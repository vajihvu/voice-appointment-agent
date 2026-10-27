"""Plivo XML (Speak, Stream, Dial) generators using standard Python XML library."""

import xml.etree.ElementTree as ET


def generate_stream_xml(
    websocket_url: str,
    bidirectional: bool = True,
    keep_call_alive: bool = True,
    content_type: str = "audio/x-mulaw;rate=8000",
) -> str:
    """Constructs Plivo XML response to start bidirectional audio streaming."""
    response = ET.Element("Response")
    stream = ET.SubElement(
        response,
        "Stream",
        {
            "bidirectional": str(bidirectional).lower(),
            "keepCallAlive": str(keep_call_alive).lower(),
            "contentType": content_type,
        },
    )
    stream.text = websocket_url

    xml_bytes = ET.tostring(response, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


def generate_speak_xml(text: str, voice: str = "WOMAN", language: str = "en-US") -> str:
    """Constructs Plivo XML response to speak a simple TTS message."""
    response = ET.Element("Response")
    speak = ET.SubElement(response, "Speak", {"voice": voice, "language": language})
    speak.text = text

    xml_bytes = ET.tostring(response, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


def generate_transfer_xml(
    destination_number: str,
    caller_id: str | None = None,
) -> str:
    """Constructs Plivo XML response to forward a call to a human receptionist/doctor."""
    response = ET.Element("Response")
    dial_attrs = {}
    if caller_id:
        dial_attrs["callerId"] = caller_id

    dial = ET.SubElement(response, "Dial", dial_attrs)
    number = ET.SubElement(dial, "Number")
    number.text = destination_number

    xml_bytes = ET.tostring(response, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")
