"""
TODO List
    * untested code
"""
from playground.network.common import StackingProtocolFactory, StackingProtocol, StackingTransport

from playground.network.packet.fieldtypes import BOOL, UINT32, BUFFER, STRING
from playground.network.common import PlaygroundAddress

# MessageDefinition is the base class of all automatically serializable messages
from playground.network.packet import PacketType
import playground

import sys
import time
import os
import logging
import asyncio
import random
import hashlib
#logger = logging.getLogger(__name__)
seqClientDictionary = {}
seqServerDictionary = {}
PACKET_MAX_SIZE = 50


class PIMPPacket(PacketType):
    """
    EchoProtocolPacket is a simple message for sending a bit of
    data and getting the same data back as a response (echo). The
    "header" is simply a 1-byte boolean that indicates whether or
    not it is the original message or the echo.
    """

    DEFINITION_IDENTIFIER = "PIMP.packet"

    DEFINITION_VERSION = "1.0"

    FIELDS = [
        ("seqNum", UINT32),
        ("ackNum", UINT32),
        ("ACK", BOOL),
        ("RST", BOOL),
        ("SYN", BOOL),
        ("FIN", BOOL),
        ("RTR", BOOL),
        ("checkSum", BUFFER),
        ("data", BUFFER)
    ]

def create_packet(**config):
    packet = PIMPPacket()
    packet.seqNum = config.get("seqNum", 0)
    packet.ackNum = config.get("ackNum", 0)
    packet.SYN    = config.get("SYN",False)
    packet.ACK    = config.get("ACK",False)
    packet.RST    = config.get("RST",False)
    packet.RTR    = config.get("RTR",False)
    packet.FIN    = config.get("FIN",False)
    packet.data   = config.get("data", b"")
    packet.checkSum = b""
    packet.checkSum = hashlib.md5(packet.__serialize__()).digest()
    return packet

class PIMPTransport(StackingTransport):
    def write(self, data):
        # @hint: For higher layer protocol to write the data
        # if close = true: close()
        seqNum = random.randint(1, 2147483647//10)
        while(len(data) >= PACKET_MAX_SIZE):
            pimpPacket = create_packet(seqNum=seqNum)

            pimpPacket.data = data[:PACKET_MAX_SIZE]
            pimpPacket.checkSum = self.calculate_checksum(pimpPacket)
            self.lowerTransport().write(pimpPacket.__serialize__())
            print("DEBUGGG: Data: ", data)
            print("DEBUGGG: Data Length ", len(data))
            print("Teardown packet sent!")

            # @hint: After sending out one of the teardown packet, update "data" & "seqNum"
            data = data[PACKET_MAX_SIZE:len(data)]
            seqNum += 1

        pimpPacket = create_packet(seqNum=seqNum)
        pimpPacket.data = data
        new_checksum = self.calculate_checksum(pimpPacket)
        pimpPacket.checksum = new_checksum
        self.lowerTransport().write(pimpPacket.__serialize__())
        print("DEBUGGGGG: Data: ", data)
        print("DEBUGGGGG: Data size: ", len(data))
        print("^^^ PIMPTransport sent a packet! ^^^")

    def calculate_checksum(self, pkt):
        new_checksum = b""
        new_checksum = hashlib.md5(pkt.__serialize__()).digest()
        return new_checksum

    def close(self):
        pimpPacket = create_packet(FIN=True)
        # pimpPacket.data = data
        pimpPacket.checksum = self.calculate_checksum(pimpPacket)
        self.lowerTransport().write(pimpPacket.__serialize__())
        print("** FIN packet sent! Close initiated **")


class PIMPServerProtocol(StackingProtocol):
    def __init__(self):
        super().__init__()
        self.deserializer = PIMPPacket.Deserializer()
        self.transport = None
        self.stored_number = 0
        self.established_flag = False
        self.seqServerDictionary = seqServerDictionary
        self.stateMachine = "unconnected"

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        self.higherProtocol().connection_lost(exc)

    def start_timer(self, pkt):
        if pkt in self.seqServerDictionary.values():
            self.transport.write(pkt.__serialize__())
            print("Resend packet! ", pkt.seqNum)
        else:
            print("GOOOOD!")

    def data_received(self, data):
        self.deserializer.update(data)

        for pimpPacket in self.deserializer.nextPackets():
            if self.check(pimpPacket):
                if self.stateMachine == "unconnected":
                    if pimpPacket.SYN == True and pimpPacket.ACK == False:
                        # @hint: If receive SYN Packet from client, return SYN-ACK Packet
                        print("--Received SYN Packet from client.--")

                        synackPacket = create_packet(seqNum=random.randint(1, 2147483647//10), ackNum=pimpPacket.seqNum+1, ACK=True, SYN=True)
                        synackPacket.checksum = self.calculate_checksum(synackPacket)
                        #self.transport.write(synackPacket.__serialize__())
                        self.stored_number = synackPacket.seqNum
                        new = {synackPacket.seqNum: synackPacket}
                        self.seqServerDictionary.update(new)
                        # Start timer
                        asyncio.get_event_loop().call_later(0.5, self.start_timer, synackPacket)
                        #print("**SYN-ACK Packet sent back to client!**")

                    elif pimpPacket.ACK == True and pimpPacket.SYN == False:
                        if self.checkAckNum(pimpPacket):
                            # @hint: Receive ACK Packet (3rd handshake)
                            print("3-way handshake established!")
                            self.stateMachine = "connected"
                            # @hint: Notify upper layer for connection established?
                            pimp_transport = PIMPTransport(self.transport)
                            self.higherProtocol().connection_made(pimp_transport)

                elif self.stateMachine == "connected":
                    # If three-way handshake has been established, start data tranmission!
                    if pimpPacket.ACK == True and pimpPacket.data == b"":

                        # @hint: Receive "Data-ACK"
                        # TODO: Remove that packet from the sent packet cache.
                        # @hint: Since another endpoint has just acknowledged receiving that piece of data.
                        print("Received Data ACK.")

                    elif pimpPacket.FIN == True and pimpPacket.ACK == True and pimpPacket.data == b"":
                        # TODO: If receiving FIN Packet
                        print("--Received FIN Packet--")
                        FINACKPacket = create_packet(seqNum=random.randint(1, 2147483647//10), ackNum=pimpPacket.seqNum+1, ACK=True, FIN=True)
                        FINACKPacket.checksum = self.calculate_checksum(FINACKPacket)
                        self.transport.write(FINACKPacket.__serialize__())
                        print("** FINACK packet sent! **")
                        self.established_flag == False
                        self.transport.close()
                        print("CONNECTION CLOSED!")

                    elif pimpPacket.data != b"":
                        # @hint: (1). return data ACK to client
                        dataACKPacket = create_packet(ackNum=pimpPacket.seqNum+1, ACK=True)
                        dataACKPacket.checksum = self.calculate_checksum(dataACKPacket)
                        self.transport.write(dataACKPacket.__serialize__())
                        print("Sent ACK back to client")

                        # @hint: (2). pass data to higher layer
                        self.higherProtocol().data_received(pimpPacket.data)
                        print("Pass data to application layer")

                    else:
                        print("There's an error on server side...")

                else:
                    print("*** Invalid packet is received. That packet is dropped. ***")
            else:
                # @hint: resend RTR packet with the same ACK number
                rtrPacket = create_packet(ackNum=pimpPacket.seqNum+1, RTR=True)
                rtrPacket.checksum = self.calculate_checksum(rtrPacket)
                self.transport.write(rtrPacket.__serialize__())
                print("!!! Checksum test failed. Send RTR Packet back to client! !!!")

    def checkAckNum(self, pkt):
        if pkt.ackNum-1 in self.seqServerDictionary:
            print("Received packet with correct ACK number!")
            print("@@@@@ Server cache: ", self.seqServerDictionary)
            del self.seqServerDictionary[pkt.ackNum-1]
            print("@@@@@ Updated server cache: ", self.seqServerDictionary)
            return True
        else:
            return False
        # for x in self.seqServerDictionary:
        #     if pkt.ackNum == x+1:
        #         del self.seqServerDictionary[x]
        #         return True
        #     else:
        #         return False

    def check(self, pkt):
        old_checksum = pkt.checksum
        pkt.checksum = b""
        new_checksum = b""
        new_checksum = self.calculate_checksum(pkt)
        if old_checksum == new_checksum:
            return True
        else:
            print("wrong checksum")
            return False

    def calculate_checksum(self, pkt):
        new_checksum = b""
        new_checksum = hashlib.md5(pkt.__serialize__()).digest()
        return new_checksum


class PIMPClientProtocol(StackingProtocol):
    def __init__(self):
        super().__init__()
        self.deserializer = PIMPPacket.Deserializer()
        self.transport = None
        self.stored_number = 0
        self.established_flag = False
        self.stateMachine = "unconnected"
        self.seqClientDictionary = seqClientDictionary

    def start_timer(self, pkt):
        # TODO: If sent packet still in the cache -> it means that NO ACK packet has been responsed!
        if pkt in self.seqClientDictionary.values():
            self.transport.write(pkt.__serialize__())
            print("Resend packet!", pkt.seqNum)
        else:
            print("^^ Corresponding ACK has been received! ^^")

    def connection_made(self, transport):
        # @hint: Send the SYN Packet to initiate the 3-way handshake
        self.transport = transport
        synPacket = create_packet(SYN=True)
        
        self.stored_number = synPacket.seqNum
        new = {synPacket.seqNum: synPacket}
        self.seqClientDictionary.update(new)

        self.transport.write(synPacket.__serialize__())
        print("done connection made")
        print("@@@@@@@@ Client local cache: ", self.seqClientDictionary)
        print("**SYN Packet sent!**")

        asyncio.get_event_loop().call_later(0.5, self.start_timer, synPacket)#start Timer_ SYN

    def connection_lost(self, exc):
        self.higherProtocol().connection_lost(exc)

    def data_received(self, data):
        self.deserializer.update(data)
        for pimpPacket in self.deserializer.nextPackets():
            if self.check(pimpPacket):
                if self.stateMachine == "unconnected":
                    if pimpPacket.ACK == True and pimpPacket.SYN == True:
                        if self.checkAckNum(pimpPacket): #check ACK and update dictionary
                            # @hint: If received packet's ACK number is expected
                            print("--Received SYN-ACK Packet from server.--")

                            ackPacket = create_packet(ackNum=pimpPacket.seqNum+1, ACK=True)
                            ackPacket.checksum = self.calculate_checksum(ackPacket)
                            self.transport.write(ackPacket.__serialize__())
                            print("**ACK Packet sent!**")
                            
                            # @hint: reliable transport layer connection made!
                            # @hint; notify higher layer that the connection has been established!
                            self.established_flag = True
                            self.stateMachine = "connected"
                            pimp_transport = PIMPTransport(self.transport)
                            self.higherProtocol().connection_made(pimp_transport)

                        else:
                            print("ACK number is wrong!")

                    elif pimpPacket.RTR == True:
                        # @hint: If receive RTR packet, re-send the previous sent packet!
                        for x in self.seqClientDictionary:
                            if x == pimpPacket.ackNum - 1:
                                self.transport.write(
                                    self.seqClientDictionary.get(x).__serialize__())
                                print("** RTR Packet resent! **")

                elif self.stateMachine == "connected":
                    """
                        * If receiving ACK, it means that the server has received the data packet that was just sent!
                            => TODO: remove that packet from the cache of sent packets
                        * If received packets do not have ACK flag, this means that those packets are "Data Packet" sent by the server.
                            Therefore, return ACKnowledgment back.
                    """
                    # @hint" Receive data ACK from server on PIMP layer!
                    if pimpPacket.ACK == True and pimpPacket.data == b"":
                        # TODO: remove that sent packet from the local cache
                        print("--- Received data ACK.---")

                    elif pimpPacket.FIN == True and pimpPacket.ACK == True and pimpPacket.data == b"":
                        # @hint: Receive FIN-ACK Packet
                        print("--- Receive FIN-ACK packet from server. ---")
                        ackPacket = create_packet(ackNum=pimpPacket.seqNum+1, ACK=True)
                        ackPacket.checksum = self.calculate_checksum(ackPacket)
                        self.transport.write(ackPacket.__serialize__())
                        print("** ACK Packet sent to close the connection. **")
                        self.established_flag == False
                        self.transport.close()
                        print("CONNECTION CLOSED!")

                    elif pimpPacket.data != b"0":
                        # @hint: Contruct Data ACK packet and sent back to server
                        dataACKPacket = create_packet(seqNum=0, ackNum=pimpPacket.seqNum+1, ACK=True)
                        dataACKPacket.checksum = self.calculate_checksum(dataACKPacket)
                        self.transport.write(dataACKPacket.__serialize__())
                        print("Sent ACK back to client")

                        # @hint: pass data to higher layer
                        self.higherProtocol().data_received(pimpPacket.data)

                    else:
                        print("OOP! There's an error on client side")

                else:
                    print("_____OOPS!!_____")

    def checkAckNum(self, pkt):
        if pkt.ackNum == self.stored_number + 1:
            print("Received packet with correct ACK number!")
            print("@@@@@ Client cache: ", self.seqClientDictionary)
            del self.seqClientDictionary[self.stored_number]
            print("@@@@@ Updated client cache: ", self.seqClientDictionary)
            return True
        else:
            return False
        # for x in self.seqClientDictionary:
        #     if pkt.ackNum == x+1:
        #         del self.seqClientDictionary[x]
        #         return True
        #     else:
        #         return False

    def check(self, pkt):
        old_checksum = pkt.checksum
        pkt.checksum = b""
        new_checksum = b""
        new_checksum = self.calculate_checksum(pkt)
        if old_checksum == new_checksum:
            return True
        else:
            print("wrong checksum. Packet is corrupted!")
            return False

    def calculate_checksum(self, pkt):
        new_checksum = b""
        new_checksum = hashlib.md5(pkt.__serialize__()).digest()
        # @hint: Return in "bytes" instead of "string"
        return new_checksum


USAGE = """usage: echotest <mode> [-stack=<stack_name>]
  mode is either 'server' or a server's address (client mode)"""

if __name__ == "__main__":
    echoArgs = {}

    stack = "default"

    args = sys.argv[1:]
    i = 0
    for arg in args:
        if arg.startswith("-"):
            k, v = arg.split("=")
            echoArgs[k] = v
        else:
            echoArgs[i] = arg
            i += 1

    if "-stack" in echoArgs:
        stack = echoArgs["-stack"]

    if not 0 in echoArgs:
        sys.exit(USAGE)

    mode = echoArgs[0]
    loop = asyncio.get_event_loop()
    # loop.set_debug(enabled=True)
    #from playground.common.logging import EnablePresetLogging, PRESET_DEBUG
    # EnablePresetLogging(PRESET_DEBUG)

    if mode.lower() == "server":
        coro = playground.create_server(
            lambda: PIMPServerProtocol(), port=101, family=stack)
        server = loop.run_until_complete(coro)
        print("Echo Server Started at {}".format(
            server.sockets[0].gethostname()))
        loop.run_forever()
        loop.close()

    else:
        remoteAddress = mode
        coro = playground.create_connection(lambda: PIMPClientProtocol(),
                                            host=remoteAddress,
                                            port=101,
                                            family=stack)
        transport, protocol = loop.run_until_complete(coro)
        # print("Echo Client Connected. Starting UI t:{}. p:{}".format(
        # transport, protocol))
        loop.run_forever()
        loop.close()


PIMPClientFactory = StackingProtocolFactory.CreateFactoryType(
    lambda: PIMPClientProtocol())
PIMPServerFactory = StackingProtocolFactory.CreateFactoryType(
    lambda: PIMPServerProtocol())
