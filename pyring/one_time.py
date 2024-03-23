# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import dataclasses
import functools
import operator
from typing import ByteString, List

from .ge import Point, G, hash_to_scalar
from .sc25519 import Scalar


class PrivateKey:
    __slots__ = ["scalar"]

    def __init__(self, scalar: Scalar) -> None:
        self.scalar = scalar

    @classmethod
    def generate(cls) -> PrivateKey:
        return cls(Scalar.random())

    @classmethod
    def from_private_bytes(cls, data: ByteString) -> PrivateKey:
        return cls(Scalar(bytes(data)))

    def public_key(self) -> PublicKey:
        # Note that this is not a standard Ed25519 public key
        # The regular method described in RFC8032 involves hashing
        # the secret scalar and pruning bits.
        # (c.f. https://tools.ietf.org/html/rfc8032#section-5.1.5 and
        # https://github.com/openssl/openssl/blob/36e619d70f86f9dd52c57b6ac8a3bfea3c0a2745/crypto/ec/curve25519.c#L5544)
        # but this destroys the associativity and distributivity
        # properties needed for the ring construction
        return PublicKey(self.scalar * G)

    def key_image(self) -> Point:
        return self.scalar * self.public_key().point.hash_to_point()


class PublicKey:
    __slots__ = ["point"]

    def __init__(self, point: Point) -> None:
        self.point = point


@dataclasses.dataclass(frozen=True)
class RingSignature:
    """A ring signature.

    A ring signature consists of the public keys the message was signed against, the
    key image of the signer's public key, and the two rings.
    """

    public_keys: List[Point]
    key_image: Point
    c: List[Scalar]
    r: List[Scalar]


@dataclasses.dataclass(frozen=True)
class WithinRingSignature:
    """A within ring signature.

    A within ring signature consists of the public keys the message was signed against, the
    encrypted key images of the signer's public key, and the two rings.
    """

    public_keys: List[Point]
    public_points: List[Point]
    enc_points: List[Point]
    c: List[Scalar]
    r: List[Scalar]


def sign(
    message: ByteString, public_keys: List[Point], private_key: Scalar, key_index: int
) -> RingSignature:
    """Sign the given message.

    As part of the signature generation, the public keys are shuffled so that the
    ordering holds no information about the identity of the signer.

    Args:
        message: The message to sign.
        public_keys: The public keys of the group to generate a ring signature of.
        private_key: The secret key of the signer.
        key_index: The index to the corresponding public key. Note that they key
            index should be unpredictable; shuffle the public keys before generating
            the ring signature if this is not the case.

    Returns:
        A ring signature.
    """
    # We follow the notation from the CryptoNote white paper, section 4.4
    x = private_key
    s = key_index
    I = PrivateKey(private_key).key_image()  # noqa: E741
    H_s = hash_to_scalar

    def H_p(point: Point) -> Point:
        return point.hash_to_point()

    buffer_ = bytearray(message)

    c = []
    r = []
    for i, P_i in enumerate(public_keys):
        if i == key_index:
            q_s = Scalar.random()
            buffer_ += (q_s * G).as_bytes()
            buffer_ += (q_s * H_p(P_i)).as_bytes()
        else:
            q_i = Scalar.random()
            w_i = Scalar.random()
            c.append(w_i)
            r.append(q_i)
            buffer_ += (q_i * G + w_i * P_i).as_bytes()
            buffer_ += (q_i * H_p(P_i) + w_i * I).as_bytes()
    c.insert(s, H_s(buffer_) - functools.reduce(operator.add, c))
    r.insert(s, q_s - c[s] * x)

    return (public_keys, I, c, r)

def ring_sign(
    message: ByteString, public_keys: List[Point], private_key: Scalar, key_index: int
) -> RingSignature:
    public_keys, I, c, r = sign(message, public_keys, private_key, key_index)
    return RingSignature(public_keys, I, c, r)

def within_ring_sign(
    message: ByteString, public_keys: List[Point], private_key: Scalar, key_index: int
) -> RingSignature:
    public_keys, I, c, r = sign(message, public_keys, private_key, key_index)

    public_points = []
    enc_points = []
    for public_key in public_keys:
        r_i = Scalar.random()
        shared_secret = r_i * public_key
        public = r_i * G
        public_points.append(public)
        enc_points.append(shared_secret + I)
    return WithinRingSignature(public_keys, public_points, enc_points, c, r)

def ring_verify(message: ByteString, signature: RingSignature) -> bool:
    """Verify that a signature is valid for the given message.

    Args:
        message: The message to verify the signature for.
        signature: The ring signature to verify.
    """
    public_keys = signature.public_keys
    I, c, r = signature.key_image, signature.c, signature.r
    H_s = hash_to_scalar

    def H_p(point: Point) -> Point:
        return point.hash_to_point()

    buffer_ = bytearray(message)
    for i, (P_i, r_i, c_i) in enumerate(zip(public_keys, r, c)):
        buffer_ += (r_i * G + c_i * P_i).as_bytes()
        buffer_ += (r_i * H_p(P_i) + c_i * I).as_bytes()

    return H_s(buffer_) - functools.reduce(operator.add, c) == 0

def within_ring_verify(message: ByteString, signature: WithinRingSignature, private_key: Scalar) -> bool:
    index = signature.public_keys.index(PrivateKey(private_key).public_key().point)
    public_point = signature.public_points[index]
    enc_point = signature.enc_points[index]
    shared_secret = private_key * public_point
    key_image = enc_point - shared_secret
    ring_signature = RingSignature(signature.public_keys, key_image, signature.c, signature.r)
    return ring_verify(message, ring_signature)
