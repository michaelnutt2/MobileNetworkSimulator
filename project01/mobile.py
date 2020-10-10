from socket import *
from threading import Thread, Event
import argparse

def pilot():
    """ Runs on startup to receive Base Station information

    Returns Base Station IP address, should take max 5 seconds
    to receive information based on broadcast frequency
    """
    msg = ''
    pilot_socket = socket(AF_INET, SOCK_DGRAM)
    pilot_socket.bind(('<broadcast>', 2055))
    while msg != 'PILOT':
        print('Searching for network...')
        pilot_msg = pilot_socket.recvfrom(255)
        msg = pilot_msg[0].decode('utf-8')
    print('Connected to network')
    pilot_socket.close()
    return pilot_msg[1][0]
    

def start_call(base_station_ip, target_msn):
    """Handles setting up call

    Sends initial SETUP MSN message to broadcast station
    simulator, then waits for replies following event flow
    as seen in report

    Arguments:
    base_station_ip -- IP address detected through pilot function
    target_msn -- Mobile Station Number of phone we are calling
    """
    
    # Set up socket to initiate call
    traffic_socket = socket(AF_INET, SOCK_STREAM)
    traffic_socket.connect((base_station_ip, 2166))

    setup_msg = 'SETUP '+target_msn
    setup_msg_encoded = setup_msg.encode('utf-8')

    # send setup message
    traffic_socket.sendall(setup_msg_encoded)

    # Wait for confirmation response from server
    msg = traffic_socket.recv(255)
    print(msg)

    # Wait for ringing message from receiving mobile
    msg = traffic_socket.recv(255)
    print(msg)

    # Wait for connected message from mobile
    msg = traffic_socket.recv(255)
    print(msg)

    ok_msg = 'OK'
    traffic_socket.sendall(ok_msg.encode('utf-8'))

    # Start call teardown, send end call message
    end_call_msg = 'END CALL'.encode('utf-8')
    traffic_socket.sendall(end_call_msg)

    # Wait for confirmation message from receiver
    call_ended_msg = traffic_socket.recv(255)
    print(call_ended_msg)

    traffic_socket.close()


def page_channel(name, base_station_ip):
    """ Runs in background to receive calls from base station

    Interrupts main process with call log updates as call comes in

    Arguments:
    name -- MSN of the current phone
    base_station_ip -- IP address of the base station
    """

    # Creates setup message and source_name of the message received
    if name == 'MS2':
        setup = 'SETUP MS2'
        source_name = 'MS1'
    else:
        setup = 'SETUP MS1'
        source_name = 'MS2'

    # Sets up broadcast receiver to receive page messages
    page_socket = socket(AF_INET, SOCK_DGRAM)
    page_socket.bind(('<broadcast>', 2077))

    page_msg = page_socket.recvfrom(255)

    msg = page_msg[0].decode('utf-8')

    # Checks if the page message is intended for this phone
    # discards if not
    if msg == setup:
        page_socket.close()
        print(msg)
        recv_call(source_name, base_station_ip)


def recv_call(name, base_station_ip):
    """ Called from the paging thread, handles receiving call from base station

    Sends status messages RINGING and CONNECT after paged

    Arguments:
    name -- msn of the calling phone
    base_station_ip -- IP address of the base station call is coming from
    """
    traffic_socket = socket(AF_INET, SOCK_STREAM)
    traffic_socket.connect((base_station_ip, 2166))

    ringing = 'RINGING '+name
    traffic_socket.sendall(ringing.encode('utf-8'))
    print(ringing)

    ok = traffic_socket.recv(255)
    print(ok)

    connect_msg = 'CONNECT '+name
    traffic_socket.sendall(connect_msg.encode('utf-8'))
    print(connect_msg)

    # Wait for end call message
    end_call_msg = traffic_socket.recv(255)
    print(end_call_msg)

    # Send call end confirmation
    call_end_msg = 'CALL ENDED'.encode('utf-8')
    traffic_socket.sendall(call_end_msg)

    print(call_end_msg)

    traffic_socket.close()


def menu(name):
    """ Creates menu for phone simulator
    """
    if name == 'MS1':
        target_msn = 'MS2'
    else:
        target_msn = 'MS1'
    
    ans = 99

    options = [
        '1. Call '+target_msn,
        '2. Prepare to receive call',
        '3. Quit'
    ]

    print(len(options))

    while ans > len(options) or ans <= 0:
        print("Select an option:")
        for option in options:
            print(option)

        ans = int(input())

        if ans > len(options) or ans <= 0:
            print("Invalid input")

    return ans, target_msn


def main():
    try:
        # Parse command line arguments to define the phone identity
        parser = argparse.ArgumentParser(description='Mobile Station Simulator')
        parser.add_argument('msn', metavar='mobile_station_number', type=int, nargs=1,
            help='an integer defining mobile station number')
        args = parser.parse_args()
        name = 'MS'+str(args.msn[0])

        base_station_ip = pilot()

        while True:
            option, target_msn = menu(name)

            if option == 1:
                start_call(base_station_ip, target_msn)
            elif option == 2:
                page_channel(name, base_station_ip)
            elif option == 3:
                return

    except KeyboardInterrupt:
        return


if __name__ == '__main__':
    main()