from socket import *
from threading import Thread, Event
import argparse

def pilot():
    msg = ''
    pilot_socket = socket(AF_INET, SOCK_DGRAM)
    pilot_socket.bind(('<broadcast>', 2055))
    while msg != 'PILOT':
        print('Searching for network...')
        pilot_msg = pilot_socket.recvfrom(255)
        msg = pilot_msg[0].decode('utf-8')
    print('received IP '+pilot_msg[1][0])
    pilot_socket.close()
    return pilot_msg[1][0]
    

def start_call(base_station_ip, target_msn):
    print('About to call')
    
    # Set up socket to initiate call
    traffic_socket = socket(AF_INET, SOCK_STREAM)
    traffic_socket.connect((base_station_ip, 2166))

    setup_msg = 'SETUP '+target_msn
    setup_msg_encoded = setup_msg.encode('utf-8')

    # send setup message
    traffic_socket.sendall(setup_msg_encoded)

    print('Setup message sent')

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

    print('OK message sent')


def page_channel(name, base_station_ip):
    if name == 1:
        setup = 'SETUP MS2'
        source_name = 'MS2'
    else:
        setup = 'SETUP MS1'
        source_name = 'MS1'

    print('Inside page channel thread')

    page_socket = socket(AF_INET, SOCK_DGRAM)
    page_socket.bind('<broadcast>', 2077)

    page_msg = page_socket.recvfrom(255)

    msg = page_msg[0].decode('utf-8')
    if msg == setup:
        page_socket.close()
        print(msg)
        print('Inside page setup')
        recv_call(source_name, base_station_ip)


def recv_call(name, base_station_ip):
    traffic_socket = socket(AF_INET, SOCK_DGRAM)
    traffic_socket.connect((base_station_ip, 2166))

    ringing = 'RINGING '+name
    traffic_socket.sendall(ringing.encode('utf-8'))
    print(ringing)

    ok = traffic_socket.recv(255)
    print(ok)

    connect_msg = 'CONNECT '+name
    traffic_socket.sendall(connect_msg.encode('utf-8'))
    print(connect_msg)


def menu(name):
    if name == 'MS1':
        target_msn = 'MS2'
    else:
        target_msn = 'MS1'
    
    print("Select an option:")
    print("1. Call "+target_msn)

    ans = input()

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

        if name == 'MS1':
            option, target_msn = menu(name)

            if option == '1':
                start_call(base_station_ip, target_msn)
        else:
            page_channel(name, base_station_ip)
    except KeyboardInterrupt:
        return


if __name__ == '__main__':
    main()