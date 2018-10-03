# Opening Images in Python
# How to use the Pillow library

from PIL import Image
img = Image.open("./images/alice.png")
img.show()

##
# Asking User to Verify a PNG Signature¶
# Requesting user input. Does the supplied signature photo make sense?


def validate():
    user_input = input('Is this a valid signature? (y/n)')
    if user_input.lower():
        print('It\'s valid')
    elif user_input.lower() == 'n':
        print('It\'s not valid')
    else:
        validate()


def display_and_validate(filename):
    img = Image.open('./images/alice.png')
    img.show()
    validate()


display_and_validate('./images/alice.png')

##
# Defining the Coin
# Stupid-simple Python class


class PNGCoin:
    def __init__(self, transfers):
        self.transfers = transfers

##
# Validating a Coin
# Here we check every entry in PNGCoin.transfers


coin = PNGCoin([
    Image.open('./images/alice.png'),
    Image.open('./images/alice-to-bob.png')
])

bad_coin = PNGCoin([
    Image.open('./images/alice.png'),
    Image.open('./images/alice-to-bob-forged.png')
])


def handle_user_input(user_input):
    if user_input.lower() == 'y':
        print('It\'s valid')
        return True
    elif user_input.lower() == 'n':
        print('It\'s not valid')
        return False
    else:
        user_input = input('Is this a valid signature? (y/n)')
        handle_user_input(user_input)


def validate(coin):
    for transfer in coin.transfers:
        transfer.show()
        user_input = input('Is this a valid signature? (y/n)')
        is_valid = handle_user_input(user_input)
        if not is_valid:
            return False
    return True


validate(coin)
# validate(bad_coin)

##
# Serializing Coins
# Let's take the coin defined ^^ and write it to disk

import pickle


def serialize(coin):
    return pickle.dumps(coin)


def to_disk(coin, filename):
    serialized = serialize(coin)
    with open(filename, 'wb') as f:
        f.write(serialized)


!dir | findstr / M "bobs.pngcoin"

to_disk(coin, 'bobs.pngcoin')

!dir | findstr / M "bobs.pngcoin"

​
##
# Deserializing Coins
# Let's take the coin.pngcoin file we created ^^ and read it back into Python


def deserialize(serialized):
    return pickle.loads(serialized)


coin2 = deserialize(serialize(coin))
coin2.transfers == coin.transfers


def from_disk(filename):
    with open(filename, 'rb') as f:
        serialized = f.read()
        return deserialize(serialized)


coin3 = from_disk('bobs.pngcoin')
coin3.transfers == coin.transfers

​
##
# Using the Final Library
# I also wrote a pngcoin.py library that uses a more object-oriented design. Let's explore how it works:

import PNGCoin

coin = PNGCoin.PNGCoin([
    Image.open('./images/alice.png'),
    Image.open('./images/alice-to-bob.png')
])

coin.validate()

coin.to_disk('library-example.pngcoin')

coin = PNGCoin.PNGCoin.from_disk('library-example.pngcoin')

coin.validate()
