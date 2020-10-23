from socket import *
from threading import Thread, Event
import argparse
import select
import sys

# Constants
PILOT_PORT = 2055
TRAFFIC_PORT = 2166
PAGING_PORT = 2077
FATAL_ERR = object()

def pilot():
    """ Runs on startup to receive Base Station information

    Returns Base Station IP address, should take max 5 seconds
    to receive information based on broadcast frequency
    """
    msg = ''
    pilot_socket = socket(AF_INET, SOCK_DGRAM)
    pilot_socket.bind(('<broadcast>', PILOT_PORT))
    while msg != 'PILOT':
        print('Searching for network...')
        pilot_msg = pilot_socket.recvfrom(255)
        
        msg = pilot_msg[0].decode('utf-8')
    print('Connected to network')
    pilot_socket.close()
    return pilot_msg[1][0]
    

def start_call(args):
    """Handles setting up call

    Sends initial SETUP MSN message to broadcast station
    simulator, then waits for replies following event flow
    as seen in report

    Arguments:
    args -- dictionary that contains the following arguments:
        base_station_ip -- IP address detected through pilot function
        target_msn -- Mobile Station Number of phone we are calling
    """
    
    base_station_ip = args["base_station_ip"]
    target_msn = args["target_msn"]
    msn = args["name"]

    # Set up socket to initiate call
    traffic_socket = socket(AF_INET, SOCK_STREAM)
    traffic_socket.connect((base_station_ip, TRAFFIC_PORT))

    setup_msg = msn+' SETUP '+target_msn
    setup_msg_encoded = setup_msg.encode('utf-8')

    # send setup message
    traffic_socket.sendall(setup_msg_encoded)

    # Wait for confirmation response from server
    msg = traffic_socket.recv(255)
    if not msg:
        traffic_socket.close()
        print('CONNECTION LOST')
        return
    
    print(msg)

    # Wait for ringing message from receiving mobile
    msg = traffic_socket.recv(255)
    if not msg:
        traffic_socket.close()
        print('CONNECTION LOST')
        return

    print(msg)

    # Wait for connected message from mobile
    msg = traffic_socket.recv(255)
    if not msg:
        traffic_socket.close()
        print('CONNECTION LOST')
        return

    print(msg)

    ok_msg = 'OK'
    traffic_socket.sendall(ok_msg.encode('utf-8'))

    timeout = 2
    while True:
        try:
            sys.stdin.flush()
            read_list, _, _ = select.select([traffic_socket, sys.stdin], [], [], timeout)
            if not read_list:
                continue
            if read_list[0] == traffic_socket:
                msg = traffic_socket.recv(255)
                print(msg)
                if msg.decode('utf-8') == 'END CALL':
                    traffic_socket.sendall('CALL ENDED'.encode('utf-8'))
                    traffic_socket.close()
            else:
                msg = input()
                traffic_socket.sendall(msg.encode('utf-8'))
                if msg == 'END CALL':
                    # Wait for confirmation message
                    call_ended_msg = traffic_socket.recv(255)
                    if not call_ended_msg:
                        print('CONNECTION LOST')
                    print(call_ended_msg)
                    traffic_socket.close()
                    return
        except ValueError:
            print('CONNECTION LOST')
            traffic_socket.close()
            return


def page_channel(args):
    """ Runs in background to receive calls from base station

    Interrupts main process with call log updates as call comes in

    Arguments:
    args -- dictionary that contains the following arguments:
        name -- MSN of the current phone
        base_station_ip -- IP address of the base station
    """

    name = args["name"]
    base_station_ip = args["base_station_ip"]

    # Creates setup message and source_name of the message received
    if name == 'MS2':
        setup = 'MS1 SETUP MS2'
        source_name = 'MS1'
    else:
        setup = 'MS2 SETUP MS1'
        source_name = 'MS2'

    # Sets up broadcast receiver to receive page messages
    page_socket = socket(AF_INET, SOCK_DGRAM)
    page_socket.bind(('<broadcast>', PAGING_PORT))

    page_msg = page_socket.recvfrom(255)

    msg = page_msg[0].decode('utf-8')

    # Checks if the page message is intended for this phone
    # discards if not
    if msg == setup:
        page_socket.close()
        print(msg)
        return source_name


def recv_call(args):
    """ Called from the paging thread, handles receiving call from base station

    Sends status messages RINGING and CONNECT after paged

    Arguments:
    args -- dictionary that contains the following arguments:
        base_station_ip -- IP address of the base station call is coming from
    """

    name = page_channel(args)
    msn = args['name']
    base_station_ip = args["base_station_ip"]


    traffic_socket = socket(AF_INET, SOCK_STREAM)
    traffic_socket.connect((base_station_ip, TRAFFIC_PORT))

    ringing = msn+' RINGING '+name
    traffic_socket.sendall(ringing.encode('utf-8'))
    print(ringing)

    ok = traffic_socket.recv(255)
    print(ok)

    connect_msg = 'CONNECT '+name
    traffic_socket.sendall(connect_msg.encode('utf-8'))
    print(connect_msg)

    timeout = 2
    while True:
        try:
            sys.stdin.flush()
            read_list, _, _ = select.select([traffic_socket, sys.stdin], [], [], timeout)
            if not read_list:
                continue
            if read_list[0] == traffic_socket:
                msg = traffic_socket.recv(255)
                print(msg)
                if msg.decode('utf-8') == 'END CALL':
                    traffic_socket.sendall('CALL ENDED'.encode('utf-8'))
                    traffic_socket.close()
            else:
                msg = input()
                print(msg)
                traffic_socket.sendall(msg.encode('utf-8'))
                if msg == 'END CALL':
                    # Wait for confirmation message from receiver
                    call_ended_msg = traffic_socket.recv(255)
                    if not call_ended_msg:
                        traffic_socket.close()
                        print('CONNECTION LOST')
                        return
        except ValueError:
            print('CONNECTION LOST')
            traffic_socket.close()
            return


def simulate_call_failed(args):
    """simulates dropping call in mid set up

    This function should be called on the 'receiver'
    will stop sending setup messages to simulate losing
    network connectivity

    Arguments:
    args -- dictionary that contains the following arguments
        base_station_ip -- IP address of the base station to send messages to
    """

    name = page_channel(args)
    base_station_ip = args["base_station_ip"]

    traffic_socket = socket(AF_INET, SOCK_STREAM)
    traffic_socket.connect((base_station_ip, TRAFFIC_PORT))

    ringing = 'RINGING '+name
    traffic_socket.sendall(ringing.encode('utf-8'))
    print(ringing)
    print('CALL FAILED')
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
        '3. Simulate Call Failed',
        '4. Quit'
    ]

    # while ans > len(options) or ans <= 0:
    print("Select an option:")
    for option in options:
        print(option)

    #     ans = int(input())

    #     if ans > len(options) or ans <= 0:
    #         print("Invalid input")

    return target_msn


def main():
    try:
        # Parse command line arguments to define the phone identity
        parser = argparse.ArgumentParser(description='Mobile Station Simulator')
        parser.add_argument('msn', metavar='mobile_station_number', type=int, nargs=1,
            help='an integer defining mobile station number')
        args = parser.parse_args()
        name = 'MS'+str(args.msn[0])

        base_station_ip = pilot()

        menu_functions = {
            1: start_call,
            2: recv_call,
            3: simulate_call_failed,
            4: 'quit'
        }

        menu_args = {
            "base_station_ip": base_station_ip,
            "name": name,
            "target_msn": "",
            "sim_flag": 0
        }
        timeout = 2
        target_msn = menu(name)
        menu_args["target_msn"] = target_msn

        while True:
            # Read options from menu, call correct function and pass arguments
            sys.stdin.flush()
            read_list, _, _, = select.select([sys.stdin], [], [], timeout)
            if not read_list:
                continue
            if read_list[0] is sys.stdin:
                ans = int(input())
                print(ans)
                if ans == 4:
                    return
                elif ans > len(menu_functions) or ans <= 0:
                    print("Invalid Input")
                else:
                    menu_functions[ans](menu_args)

    except KeyboardInterrupt:
        return


if __name__ == '__main__':
    main()