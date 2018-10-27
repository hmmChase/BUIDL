"""
BlockCoin

Usage:
  BlockCoin.py serve
  BlockCoin.py ping
  BlockCoin.py tx <from> <to> <amount>
  BlockCoin.py balance <name>

Options:
  -h --help     Show this screen.
"""

import sys
sys.path.append('..')

import os
import uuid
import socket
import socketserver
import sys
import time
import logging
import threading
from copy import deepcopy
from ecdsa import SigningKey, SECP256k1
from utils import serialize, deserialize, prepare_simple_tx
from identities import user_private_key, user_public_key, bank_private_key, bank_public_key, airdrop_tx
from docopt import docopt


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)-15s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


NUM_BANKS = 3
BLOCK_TIME = 5


def spend_message(tx, index):
    tx_in = tx.tx_ins[index]
    outpoint = tx_in.outpoint
    return serialize(outpoint) + serialize(tx.tx_outs)


class Tx:

    def __init__(self, id, tx_ins, tx_outs):
        self.id = id
        self.tx_ins = tx_ins
        self.tx_outs = tx_outs

    def sign_input(self, index, private_key):
        message = spend_message(self, index)
        signature = private_key.sign(message)
        self.tx_ins[index].signature = signature

    def verify_input(self, index, public_key):
        tx_in = self.tx_ins[index]
        message = spend_message(self, index)
        return public_key.verify(tx_in.signature, message)


class TxIn:

    def __init__(self, tx_id, index, signature=None):
        self.tx_id = tx_id
        self.index = index
        self.signature = signature

    @property
    def outpoint(self):
        return (self.tx_id, self.index)


class TxOut:

    def __init__(self, tx_id, index, amount, public_key):
        self.tx_id = tx_id
        self.index = index
        self.amount = amount
        self.public_key = public_key

    @property
    def outpoint(self):
        return (self.tx_id, self.index)


class Block:

    def __init__(self, txns, timestamp=None, signature=None):
        if timestamp is None:
            timestamp = time.time()
        self.timestamp = timestamp
        self.signature = signature
        self.txns = txns

    def message(self):
        data = [self.timestamp, self.txns]
        return serialize(data)

    def sign(self, private_key):
        self.signature = private_key.sign(self.message())


class Bank:

    def __init__(self, id, private_key):
        self.id = id
        self.private_key = private_key
        self.blocks = []
        self.utxo_set = {}
        self.mempool = []
        self.peer_addresses = {(hostname, PORT)
                               for hostname in os.environ.get('PEERS').split(',')}

    def next_id(self):
        return len(self.blocks) % NUM_BANKS

    def our_turn(self):
        return self.id == self.next_id

    def update_utxo_set(self, tx):
        for tx_out in tx.tx_outs:
            self.utxo_set[tx_out.outpoint] = tx_out
        for tx_in in tx.tx_ins:
            del self.utxo_set[tx_in.outpoint]

    def issue(self, amount, public_key):
        id_ = str(uuid.uuid4())
        tx_ins = []
        tx_outs = [TxOut(tx_id=id_, index=0, amount=amount,
                         public_key=public_key)]
        tx = Tx(id=id_, tx_ins=tx_ins, tx_outs=tx_outs)

        self.update_utxo_set(tx)

        return tx

    def validate_tx(self, tx):
        in_sum = 0
        out_sum = 0
        for index, tx_in in enumerate(tx.tx_ins):
            assert tx_in.outpoint in self.utxo_set

            tx_out = self.utxo_set[tx_in.outpoint]
            # Verify signature using public key of TxOut we're spending
            public_key = tx_out.public_key
            tx.verify_input(index, public_key)

            # Sum up the total inputs
            amount = tx_out.amount
            in_sum += amount

        for tx_out in tx.tx_outs:
            out_sum += tx_out.amount

        assert in_sum == out_sum

    def handle_tx(self, tx):
        # Save to self.utxo_set if it's valid
        self.validate_tx(tx)
        self.update_utxo_set(tx)

    def handle_block(self, block):
        public_key = bank_public_key(self.next_id())
        public_key.verify(block.signature, block.message())

        for tx in block.txns:
            self.validate_tx(tx)

        for tx in block.txns:
            self.update_utxo_set(tx)

        self.blocks.append(block)

        self.schedule_next_block()

    def fetch_utxos(self, public_key):
        return [utxo for utxo in self.utxo_set.values()
                if utxo.public_key == public_key]

    def fetch_balance(self, public_key):
        # Fetch utxo associated with this public key
        unspents = self.fetch_utxos(public_key)
        # Sum the amounts
        return sum([tx_out.amount for tx_out in unspents])

    def make_block(self):
        txns = deepcopy(self.mempool)
        self.txns = []
        block = Block(txns)
        block.sign(self.private_key)
        return block

    def submit_block(self):
        block = self.make_block()

        self.handle_block(block)

        for address in self.peer_addresses:
            send_message(address, "block", block)

    def schedule_next_block(self):
        if self.our_turn:
            threading.Timer(BLOCK_TIME, self.submit_block).start()

    def airdrop(self, tx):
        assert len(self.blocks) == 0

        self.update_utxo_set(tx)

        block = Block([tx])
        self.blocks.append(block)


# server
server_host = "0.0.0.0"
PORT = 10000
bank = None


def prepare_message(command, data):
    return {
        "command": command,
        "data": data,
    }


class MyTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class TCPHandler(socketserver.BaseRequestHandler):

    def respond(self, command, data):
        response = prepare_message(command, data)
        serialized_response = serialize(response)
        self.request.sendall(serialized_response)
        print(f'Sent {response}')

    def handle(self):
        while True:
            message_data = self.request.recv(5000).strip()
            # Need to break early if we got empty bytes,
            # otherwise we get a deserialization error
            # trying to deserialize empty bytes
            if message_data == b"":
                print("Closing connection, bye!")
                break

            message = deserialize(message_data)

            logger.info(f"Received {message}")

            if message["command"] == "ping":
                self.respond("pong", "")

            if message["command"] == "balance":
                public_key = message["data"]
                balance = bank.fetch_balance(public_key)
                self.respond("balance-response", balance)

            if message["command"] == "utxo":
                public_key = message["data"]
                utxo = bank.fetch_utxos(public_key)
                self.respond("utxo-response", utxo)

            if message["command"] == "tx":
                tx = message["data"]
                try:
                    bank.handle_tx(tx)
                    self.respond("tx-response", data="accepted")
                except:
                    self.respond("tx-response", data="rejected")

            if message["block"] == "block":
                bank.handle_block(data)


def serve():
    server = socketserver.TCPServer((server_host, PORT), TCPHandler)
    server.serve_forever()


# def send_message(command, data):
#     with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#         s.connect(client_address)

#         message = prepare_message(command, data)
#         serialized_message = serialize(message)
#         s.sendall(serialized_message)

#         message_data = s.recv(5000)
#         message = deserialize(message_data)

#         print(f'Received {message}')

#         return message


def send_message(address, command, data, response=False):
    message = prepare_message(command, data)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(address)
        s.sendall(serialize(message))
        if response:
            return deserialize(s.recv(5000))


def main(args):
    if args["serve"]:
        global bank
        bank_id = int(os.environ["BANK_ID"])
        bank = Bank(
            id=bank_id,
            private_key=bank_private_key(bank_id)
        )
        bank.airdrop(airdrop_tx())
        bank.schedule_next_block()
        serve()
    elif args["ping"]:
        send_message("ping", "")
    elif args["balance"]:
        name = args["<name>"]
        public_key = user_public_key(name)
        send_message("balance", public_key)
    elif args["tx"]:
        sender_private_key = user_private_key(args["<from>"])
        recipient_public_key = user_public_key(args["<to>"])
        amount = int(args["<amount>"])
        sender_public_key = sender_private_key.get_verifying_key()

        utxo_response = send_message("utxo", sender_public_key)
        utxo = utxo_response["data"]

        tx = prepare_simple_tx(utxo, sender_private_key,
                               recipient_public_key, amount)

        response = send_message("tx", tx)
        print("response")

    else:
        print("invalid command")
        # print("python serialized_ping_pong.py <serve|ping>")


if __name__ == "__main__":
    args = docopt(__doc__)
    main(args)
