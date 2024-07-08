import datetime
import logging
import os
import re
import sys
import uuid

from cachetools import TTLCache
from tornado import gen
from urllib.parse import urlparse, urlencode
from urllib.parse import parse_qs

from pynostr.event import EventKind, Event
from pynostr.filters import Filters, FiltersList
from pynostr.message_type import RelayMessageType
from pynostr.relay_list import RelayList
from pynostr.relay_manager import RelayManager

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="[%(asctime)s - %(levelname)s] %(message)s")
logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger("StripTrackBot")

# small cache for dupl ids from several relays
small_cache = TTLCache(maxsize=200, ttl=15)
# 32 byte hex pk for publishing from env
hex_pk = os.environ.get("HEX_PK", '')
if not hex_pk:
    print("HEX_PK environment variable is not set, exiting")
    exit(-1)

# url params to strip from links
bad_params = ["utm_source", "utm_medium", "utm_campaign", "utm_term",
              "utm_content", "s", "t", "src", "ref_src", "ref_url", "twclid",
              ]


def check_urls(text_content):
    modified_content = ''
    for url in re.findall(r'(https?://\S+)', text_content):
        log.debug(f"Checking {url}")
        parsed_url = urlparse(url)
        query_dict = parse_qs(parsed_url.query)
        bad = False
        for key in list(query_dict.keys()):
            if key in bad_params:
                del query_dict[key]
                bad = True
        if bad:
            new_url = parsed_url._replace(query=urlencode(query_dict, doseq=True)).geturl()
            log.debug(f"REPLACE by new URL: {new_url}")
            text_content = text_content.replace(url, new_url)
            modified_content = text_content
    return modified_content


def publish_reply(event: Event, new_content: str):
    global relay_manager
    log.info(f"PUBLISHING {new_content}")
    new_event: Event = Event(new_content)
    new_event.add_tag("e", event.id)
    new_event.sign(hex_pk)
    relay_manager.publish_event(new_event)


@gen.coroutine
def check_message(message_json, url):
    if message_json[0] == RelayMessageType.EVENT:
        event: Event = Event.from_dict(message_json[2])
        if event.id not in small_cache:
            small_cache[event.id] = 1
            if 'http' in event.content:
                log.debug(f"{url}: {str(message_json)}")
                new_content = check_urls(event.content)
                if new_content:
                    publish_reply(event, new_content)


if __name__ == "__main__":
    # set some relays to deal with
    relays = [
        "wss://nos.lol", "wss://relay.nostr.bg",
        "wss://nostr.einundzwanzig.space", "wss://relay.damus.io",
        "wss://nostr.mom/", "wss://nostr-pub.wellorder.net/",
        "wss://relay.nostr.jabber.ch", "wss://relay.pleb.to", ]
    while True:
        log.info("The bot connects to relays now")
        relay_list = RelayList()
        relay_list.append_url_list(relays)
        relay_list.update_relay_information(timeout=0.9)
        relay_list.drop_empty_metadata()
        log.info(f"Using {len(relay_list.data)} relays...")

        # set up the relay manager
        relay_manager = RelayManager(error_threshold=3, timeout=0)
        relay_manager.add_relay_list(
            relay_list,
            close_on_eose=False,
            message_callback=check_message,
            message_callback_url=True,
        )

        # filter on text notes and subscribe
        filters = FiltersList(
            [
                Filters(
                    since=int(datetime.datetime.now().timestamp()),
                    kinds=[EventKind.TEXT_NOTE],
                )
            ]
        )
        subscription_id = uuid.uuid1().hex
        relay_manager.add_subscription_on_all_relays(subscription_id, filters)
        relay_manager.run_sync()
