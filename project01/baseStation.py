from socket import *
from threading import Thread, Event
from queue import Queue, Empty
import time
import select

# Constants
# Object to enter queues when server is shutting down
_shutdown = object()
pilot_port = 2055
traffic_port = 2166
paging_port = 2077

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
        pilot_socket.sendto(msg.encode('utf-8'), ('<broadcast>', pilot_port))


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
    print('Inside Page')
    while True:
        page_obj = page_queue.get()
        print(page_obj)
        if page_obj is _shutdown:
            break
        page_socket.sendto(page_obj, ('<broadcast>', paging_port))

def call_error(mobile_socket, err_msg):
    """Sends error message to mobile if error during call processing
    """
    mobile_socket.sendall(err_msg)
    mobile_socket.close()


def call_setup(mobile_socket, mobile_caller_queue, mobile_receiver_queue, msn, target):
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
    try:
        # Sending initial OK confirmation for setup message
        ok_msg = 'OK'.encode('utf-8')
        print(msn+':'+str(ok_msg))
        mobile_socket.sendall(ok_msg)

        # Wait for receiver Ringing Response
        try:
            ringing = mobile_caller_queue.get(timeout=5)
        except Empty:
            print(msn+': No response from receiver, unreachable')
            call_error(mobile_socket, 'NUMBER UNREACHABLE'.encode('utf-8'))
            return

        # Ensure server not shutting down
        if ringing is _shutdown:
            return
        print(msn+': '+str(ringing))
        mobile_socket.sendall(ringing)

        # Wait for Connected response
        try:
            connected = mobile_caller_queue.get(timeout=5)
        except Empty:
            print(msn+': Call Failed')
            call_error(mobile_socket, 'CALL FAILED'.encode('utf-8'))
            return

        if ringing is _shutdown:
            return
        print(msn+': '+str(connected))
        mobile_socket.sendall(connected)

        # Wait for confirmation from Mobile on connected
        ok_msg = mobile_socket.recv(255)
        print(msn+': '+str(ok_msg))
        mobile_receiver_queue.put(ok_msg)

        # Start sending/receiving traffic from user
        timeout = 2
        call_end = False
        while True:
            read_list, _, _ = select.select([mobile_socket], [], [], timeout)
            if read_list:
                msg = mobile_socket.recv(255)
                msg_decoded = msg.decode('utf-8')
                mobile_receiver_queue.put(msg)
                print(msn+': '+str(msg_decoded))
                if msg_decoded == 'END CALL':
                    call_end = True
                    break
            try:
                msg_from_receiver = mobile_caller_queue.get(timeout=2)
            except Empty:
                continue
            
            print(msg_from_receiver)
            mobile_socket.sendall(msg_from_receiver)

            if msg_from_receiver == 'END CALL':
                break
            
        if call_end:
            # Read message from receiver confirming call ended, send to mobile
            try:
                call_ended_msg = mobile_caller_queue.get(timeout=5)
            except Empty:
                call_error(mobile_socket, 'CALL ENDED')
                return
            
            print(msn+': ' +str(call_ended_msg))
            mobile_socket.sendall(call_ended_msg)
        else:
            call_ended_msg = mobile_socket.recv(255)
            if not call_ended_msg:
                mobile_socket.close()
                print(msn+': CALL FAILED')
                return
            print(msn+': '+str(call_ended_msg))
            mobile_receiver_queue.put(call_ended_msg)
    
        # close connection
        mobile_socket.close()
    except ConnectionResetError:
        print(msn+': CALL FAILED')


def call_answer(mobile_socket, mobile_caller_queue, mobile_receiver_queue, msn, caller):
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
    try:
        # send initial ok confirmation on ringing message
        ok_msg = 'OK'.encode('utf-8')
        print(msn+': '+str(ok_msg))
        mobile_socket.sendall(ok_msg)

        # Wait for receiver connected message
        connected_msg = mobile_socket.recv(255)
        if not connected_msg:
            mobile_socket.close()
            return
        
        print(msn+': '+str(connected_msg))
        mobile_caller_queue.put(connected_msg)

        # Wait for caller OK message
        try:
            ok_msg = mobile_receiver_queue.get(timeout=5)
        except Empty:
            call_error(mobile_socket, 'CALL FAILED'.encode('utf-8'))

        print(msn+': '+str(ok_msg))
        mobile_socket.sendall(ok_msg)

        timeout = 2
        call_end = False
        while True:
            read_list, _, _ = select.select([mobile_socket], [], [], timeout)
            if read_list:
                msg = mobile_socket.recv(255)
                msg_decoded = msg.decode('utf-8')
                mobile_caller_queue.put(msg)
                print(msn+': '+msg_decoded)
                if msg_decoded == 'END CALL':
                    call_end = True
                    break
            try:
                msg_from_caller = mobile_receiver_queue.get(timeout=2)
            except Empty:
                continue

            print(msg_from_caller)
            mobile_socket.sendall(msg_from_caller)

            if msg_from_caller == 'END CALL':
                break

        if call_end:
            # Read message from receiver confirming call ended, send to mobile
            try:
                call_ended_msg = mobile_receiver_queue.get(timeout=5)
            except Empty:
                call_error(mobile_socket, 'CALL ENDED')
                return

            print(msn+': '+str(call_ended_msg))
            mobile_socket.sendall(call_ended_msg)
        else:
            call_ended_msg = mobile_socket.recv(255)
            if not call_ended_msg:
                mobile_socket.close()
                print(msn+': CALL FAILEd')
                return
            print(msn+': '+str(call_ended_msg))
            mobile_caller_queue.put(call_ended_msg)

        # Wait for confirmation of call end from receiver
        # place on caller queue
        call_ended_msg = mobile_socket.recv(255)
        if not call_ended_msg:
            mobile_socket.close()
            print(msn+': CALL FAILED')
            return

        print(msn+': '+str(call_ended_msg))
        mobile_caller_queue.put(call_ended_msg)

        # Close connection
        mobile_socket.close()
    except ConnectionResetError:
        print(msn+': CALL FAILED')


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
    msg_split = msg_decode.split()
    print(msg_split)
    
    if msg_split[1] == 'SETUP':
        page_queue.put(msg)
        call_setup(mobile_socket, mobile_caller_queue, mobile_receiver_queue, msg_split[0], msg_split[2])
    else:
        mobile_caller_queue.put(msg)
        call_answer(mobile_socket, mobile_caller_queue, mobile_receiver_queue, msg_split[0], msg_split[1])


def main():
    try:
        print("Starting server...")
        print("Server Started")
        print("Use ctrl-C to close server when done")
        # Queues to handle passing messages between each of the phones
        # mobile 1 will only ever get from mobile_caller_queue and put into
        # mobile_receiver_queue and vice-versa
        mobile_caller_queue = Queue(maxsize=10)
        mobile_receiver_queue = Queue(maxsize=10)
        # Queue to talk to Pager thread to tell it which mobile to page
        page_queue = Queue(maxsize=5)
        # Event to signal that the server is closing
        close_server_event = Event()
        pilot_thread = Thread(target=pilot, args=(close_server_event,))
        pilot_thread.start()

        page_thread = Thread(target=page, args=(close_server_event, page_queue,))
        page_thread.start()

        mobile_thread_list = []

        # Set up server socket to manage mobile connections
        server_socket = socket(AF_INET, SOCK_STREAM)
        server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        server_socket.bind(('', traffic_port))
        server_socket.listen(10)
        
        # Start server to listen for incoming mobile calls
        while True:
            mobile_socket, address = server_socket.accept()
            mobile_thread = Thread(target=call_handler, args=(mobile_socket, mobile_caller_queue, mobile_receiver_queue, page_queue,))
            mobile_thread_list.append(mobile_thread)
            mobile_thread.start()

    except KeyboardInterrupt:
        print('Closing server')
        print('Ending Pilot Thread')
        close_server_event.set()
        print('Ending Pager Thread')
        page_queue.put(_shutdown)
        print('Joining Pilot and Page Threads')
        pilot_thread.join()
        page_thread.join()
        print('Joining mobile threads')
        for m_thread in mobile_thread_list:
            m_thread.join()
        print('Good bye')
        return


if __name__ == "__main__":
    main()