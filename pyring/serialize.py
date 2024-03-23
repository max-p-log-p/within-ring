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

import base64
import string
import textwrap
import uuid

import pyasn1.codec.der.encoder
import pyasn1.codec.der.decoder
import pyasn1.codec.native.decoder
from pyasn1.type.namedtype import NamedType, NamedTypes
from pyasn1.type.univ import Sequence, SequenceOf, OctetString, ObjectIdentifier

from .ge import Point
from .sc25519 import Scalar
from .one_time import RingSignature, WithinRingSignature


_PEM_OPENING = "-----BEGIN RING SIGNATURE-----"
_PEM_CLOSING = "-----END RING SIGNATURE-----"
_UUID = uuid.UUID(hex="3b5e61af-c4ec-496e-95e9-4b64bccdc809")
_OBJECT_ID = (2, 25) + tuple(_UUID.bytes)


class RingSignatureSchema(Sequence):
    """An ASN.1 schema for ring signatures.

    Ring signatures are identified with an object ID following Recommendation
    ITU-T X.667. The UUID4 used is 3b5e61af-c4ec-496e-95e9-4b64bccdc809.
    """

    componentType = NamedTypes(
        NamedType("algorithm", ObjectIdentifier(value=_OBJECT_ID)),
        NamedType("key_image", OctetString()),
        NamedType("public_keys", SequenceOf(componentType=OctetString())),
        NamedType("c", SequenceOf(componentType=OctetString())),
        NamedType("r", SequenceOf(componentType=OctetString())),
    )

class WithinRingSignatureSchema(Sequence):
    """An ASN.1 schema for within ring signatures.

    Within ring signatures are identified with an object ID following
    Recommendation ITU-T X.667. The UUID4 used is
    3b5e61af-c4ec-496e-95e9-4b64bccdc809.
    """

    componentType = NamedTypes(
        NamedType("algorithm", ObjectIdentifier(value=_OBJECT_ID)),
        NamedType("public_points", SequenceOf(componentType=OctetString())),
        NamedType("enc_points", SequenceOf(componentType=OctetString())),
        NamedType("public_keys", SequenceOf(componentType=OctetString())),
        NamedType("c", SequenceOf(componentType=OctetString())),
        NamedType("r", SequenceOf(componentType=OctetString())),
    )


def export_ring_pem(ring_signature: RingSignature) -> str:
    """Export the ring signature to a PEM file."""
    der = pyasn1.codec.der.encoder.encode(
        pyasn1.codec.native.decoder.decode(
            {
                "key_image": bytes(ring_signature.key_image.data),
                "public_keys": [
                    bytes(public_key.data) for public_key in ring_signature.public_keys
                ],
                "r": [bytes(r.data) for r in ring_signature.r],
                "c": [bytes(c.data) for c in ring_signature.c],
            },
            asn1Spec=RingSignatureSchema(),
        )
    )
    der_base64 = "\n".join(textwrap.wrap(base64.b64encode(der).decode("ascii"), 64))
    return f"{_PEM_OPENING}\n{der_base64}\n{_PEM_CLOSING}"


def export_within_ring_pem(ring_signature: WithinRingSignature) -> str:
    """Export the within ring signature to a PEM file."""
    der = pyasn1.codec.der.encoder.encode(
        pyasn1.codec.native.decoder.decode(
            {
                "public_points": [bytes(public_point.data) for public_point in ring_signature.public_points],
                "enc_points": [bytes(enc_point.data) for enc_point in ring_signature.enc_points],
                "public_keys": [
                    bytes(public_key.data) for public_key in ring_signature.public_keys
                ],
                "r": [bytes(r.data) for r in ring_signature.r],
                "c": [bytes(c.data) for c in ring_signature.c],
            },
            asn1Spec=WithinRingSignatureSchema(),
        )
    )
    der_base64 = "\n".join(textwrap.wrap(base64.b64encode(der).decode("ascii"), 64))
    return f"{_PEM_OPENING}\n{der_base64}\n{_PEM_CLOSING}"


def import_pem(signature: str) -> RingSignature:
    signature = signature.strip()
    if not signature.startswith(_PEM_OPENING) or not signature.endswith(_PEM_CLOSING):
        raise ValueError("invalid encapsulation")
    # Strip opening/closing and remove whitespace
    signature = signature[len(_PEM_OPENING) : -len(_PEM_CLOSING)]
    signature = signature.translate({ord(c): None for c in string.whitespace})

    # Decode from text to ASN.1 object
    der = base64.b64decode(signature, validate=True)
    asn1, remainder = pyasn1.codec.der.decoder.decode(der)
    if remainder:
        raise ValueError("unable to decode entire signature")

    # Check if the object identifier is correct
    if asn1["field-0"] != _OBJECT_ID:
        raise ValueError("invalid object ID")

    # Extract data
    key_image = Point(asn1["field-1"])
    public_keys = [Point(public_key) for public_key in asn1["field-2"]]
    cs = [Scalar(c) for c in asn1["field-3"]]
    rs = [Scalar(r) for r in asn1["field-4"]]

    return RingSignature(public_keys, key_image, cs, rs)

def import_pem(signature: str) -> WithinRingSignature:
    signature = signature.strip()
    if not signature.startswith(_PEM_OPENING) or not signature.endswith(_PEM_CLOSING):
        raise ValueError("invalid encapsulation")
    # Strip opening/closing and remove whitespace
    signature = signature[len(_PEM_OPENING) : -len(_PEM_CLOSING)]
    signature = signature.translate({ord(c): None for c in string.whitespace})

    # Decode from text to ASN.1 object
    der = base64.b64decode(signature, validate=True)
    asn1, remainder = pyasn1.codec.der.decoder.decode(der)
    if remainder:
        raise ValueError("unable to decode entire signature")

    # Check if the object identifier is correct
    if asn1["field-0"] != _OBJECT_ID:
        raise ValueError("invalid object ID")

    # Extract data
    public_points = [Point(public_point) for public_point in asn1["field-1"]]
    enc_points = [Point(enc_point) for enc_point in asn1["field-2"]]
    public_keys = [Point(public_key) for public_key in asn1["field-3"]]
    cs = [Scalar(c) for c in asn1["field-4"]]
    rs = [Scalar(r) for r in asn1["field-5"]]

    return WithinRingSignature(public_keys, public_points, enc_points, cs, rs)
