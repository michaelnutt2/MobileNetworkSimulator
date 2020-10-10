from socket import *
from threading import Thread, Event
from queue import Queue
import time


# Object to enter queues when server is shutting down
_shutdown = object()


def pilot(close_server_event):
    """ broadcast base station information to new mobiles connecting

    Arguments:
    close_server_event -- event that is checked before each page to ensure
    server shutdown has not occurred
    """
    msg = 'PILOT'
    pilot_socket = socket(AF_INET, SOCK_DGRAM)
    pilot_socket.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
    while True:
        if close_server_event.is_set():
            break
        time.sleep(5)
        # print('Broadcasting BS Info')
        pilot_socket.sendto(msg.encode('utf-8'), ('<broadcast>', 2055))


def page(close_server_event, page_queue):
    """ send broadcast to find the mobile that an incoming caller is trying to call
    
    Continuously reading from the page_queue, waiting when empty and broadcasting the
    mobile information when it is placed in the queue.
    
    Arguments:
    page_queue -- the queue the pager will be reading from
    """
    # Socket setup for broadcast channel
    page_socket = socket(AF_INET, SOCK_DGRAM)
    page_socket.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
    
    while True:
        page_obj = page_queue.get()
        if page_obj is _shutdown:
            break
        print(page_obj)
        page_socket.sendto(page_obj, ('<broadcast>', 2077))


def call_setup(mobile_socket, mobile_caller_queue, mobile_receiver_queue):
    """ Setup call for calling phone

    Provides means to communicate between this thread and the receiving phone thread
    and socket communication to send messages to the calling phone
    
    Arguments:
    mobile_socket -- socket used to send messages to phone that is connected
    mobile_caller_queue -- used by initial caller to receive messages
        used by call receiver to send messages
    mobile_receiver_queue -- used by initial caller to send messages
        used by call receiver to receive messages
    """
    # Sending initial OK confirmation for setup message
    ok_msg = 'OK'.encode('utf-8')
    print('CALLER: '+str(ok_msg))
    mobile_socket.sendall(ok_msg)

    # Wait for receiver Ringing Response
    ringing = mobile_caller_queue.get()

    # Ensure server not shutting down
    if ringing is _shutdown:
        return
    print('CALLER: '+str(ringing))
    mobile_socket.sendall(ringing)

    # Wait for Connected response
    connected = mobile_caller_queue.get()
    if ringing is _shutdown:
        return
    print('CALLER: '+str(connected))
    mobile_socket.sendall(connected)

    # Wait for confirmation from Mobile on connected
    ok_msg = mobile_socket.recv(255)
    print('CALLER: '+str(ok_msg))
    mobile_receiver_queue.put(ok_msg)

    mobile_socket.close()


def call_answer(mobile_socket, mobile_caller_queue, mobile_receiver_queue):
    """ Setup call for receiving phone

    Provides means to communicate between this thread and the calling phone thread
    and socket communication to send messages to the receiving phone
    
    Arguments:
    mobile_socket -- socket used to send messages to phone that is connected
    mobile_caller_queue -- used by initial caller to receive messages
        used by call receiver to send messages
    mobile_receiver_queue -- used by initial caller to send messages
        used by call receiver to receive messages
    """
    # send initial ok confirmation on ringing message
    ok_msg = 'OK'.encode('utf-8')
    print('RECEIVER: '+str(ok_msg))
    mobile_socket.sendall(ok_msg)

    # Wait for receiver connected message
    connected_msg = mobile_socket.recv(255)
    print('RECEIVER: '+str(connected_msg))
    mobile_caller_queue.put(connected_msg)

    # Wait for caller OK message
    ok_msg = mobile_receiver_queue.get()
    print('RECEIVER: '+str(ok_msg))
    mobile_socket.sendall(ok_msg)

    mobile_socket.close()



def call_handler(mobile_socket, mobile_caller_queue, mobile_receiver_queue, page_queue):
    """ handles incoming calls, moving to call_setup or call_answer

    Arguments:
    mobile_socket -- socket to send messages to connected caller
    mobile_caller_queue -- used by initial caller to receive messages
        used by call receiver to send messages
    mobile_receiver_queue -- used by initial caller to send messages
        used by call receiver to receive messages
    """
    msg = mobile_socket.recv(255)
    msg_decode = msg.decode('utf-8')
    
    print('Inside call handler:' + str(msg))
    if msg_decode[0:5] == 'SETUP':
        page_queue.put(msg)
        call_setup(mobile_socket, mobile_caller_queue, mobile_receiver_queue)
    else:
        mobile_caller_queue.put(msg)
        call_answer(mobile_socket, mobile_caller_queue, mobile_receiver_queue)


def main():
    try:
        print("Starting server...")
        # Queues to handle passing messages between each of the phones
        # mobile 1 will only ever get from mobile_caller_queue and put into
        # mobile_receiver_queue and vice-versa
        mobile_caller_queue = Queue(maxsize=1)
        mobile_receiver_queue = Queue(maxsize=1)
        # Queue to talk to Pager thread to tell it which mobile to page
        page_queue = Queue(maxsize=5)
        # Event to signal that the server is closing
        close_server_event = Event()
        pilot_thread = Thread(target=pilot, args=(close_server_event,))
        pilot_thread.start()

        page_thread = Thread(target=page, args=(close_server_event, page_queue,))
        page_thread.start()

        mobile_thread_list = []

        server_socket = socket(AF_INET, SOCK_STREAM)
        server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        server_socket.bind(('', 2166))
        print('Socket Bound')
        server_socket.listen(10)
        
        # Start server to listen for incoming mobile calls
        while True:
            print('Waiting for connection...')
            mobile_socket, address = server_socket.accept()
            mobile_thread = Thread(target=call_handler, args=(mobile_socket, mobile_caller_queue, mobile_receiver_queue, page_queue,))
            mobile_thread_list.append(mobile_thread)
            mobile_thread.start()

    except KeyboardInterrupt:
        close_server_event.set()
        page_queue.put(_shutdown)
        pilot_thread.join()
        page_thread.join()
        for m_thread in mobile_thread_list:
            m_thread.join()
        return


if __name__ == "__main__":
    main()