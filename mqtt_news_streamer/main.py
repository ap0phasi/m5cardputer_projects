import urllib.request
import feedparser
import paho.mqtt.client as mqtt
import time
import json


# Base api query url
base_url = 'http://export.arxiv.org/api/query?'
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
MQTT_QUERY_TOPIC = "cardputer/query"
MQTT_TOPICS = [
                "cardputer/corner/0",
                "cardputer/corner/1",
                "cardputer/corner/2",
                "cardputer/corner/3"
                ]

# Global state
feed = None
requery_flag = False
search_query = 'all:ai'  # default search query

# MQTT callbacks
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT Broker: {MQTT_BROKER}")
        # Subscribe to query topic
        client.subscribe(MQTT_QUERY_TOPIC)
        print(f"Subscribed to {MQTT_QUERY_TOPIC}")
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    global requery_flag, search_query
    if msg.topic == MQTT_QUERY_TOPIC:
        new_query = msg.payload.decode('utf-8').strip()
        if new_query:
            print(f"\nReceived query: '{new_query}'")
            search_query = f'all:{new_query}'
            requery_flag = True

def fetch_feed(query_string):
    """Fetch and parse the feed for a given query."""
    start = 0
    max_results = len(MQTT_TOPICS)
    
    query = 'search_query=%s&start=%i&max_results=%i' % (query_string,
                                                         start,
                                                         max_results)
    print(f"Fetching: {query}")
    
    try:
        # perform a GET request using the base_url and query
        response = urllib.request.urlopen(base_url + query, timeout=10).read()
        
        # parse the response using feedparser
        parsed_feed = feedparser.parse(response)
        
        print(f'Feed entries: {len(parsed_feed.entries)}')
        if parsed_feed.entries:
            entry = parsed_feed.entries[0]
            print('First entry:')
            print('Title:', entry.title)
            print('Published:', entry.published)
            print('Summary:', entry.summary[:100] + '...')
        
        return parsed_feed
    
    except Exception as e:
        print(f"ERROR fetching feed: {e}")
        print("Continuing with previous feed...")
        return None


client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
print(f"Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)

# Initial fetch
feed = fetch_feed(search_query)

MESSAGE_LEN = 100
client.loop_start()  # Start MQTT loop in background

io = 0
try:
    while True:
        # Check if we need to requery
        if requery_flag:
            print(f"\nRequerying with: {search_query}")
            new_feed = fetch_feed(search_query)
            if new_feed and new_feed.entries:  # Only update if fetch succeeded
                feed = new_feed
                io = 0  # Reset streaming position
            else:
                print("Failed to fetch new feed, keeping existing content")
            requery_flag = False
        
        # Stream the summary in chunks
        if feed and feed.entries:
            for ie, entry in enumerate(feed.entries):
                MQTT_TOPIC = MQTT_TOPICS[ie]
                i = io % len(entry.summary)
                payload = json.dumps({'title':entry.title, 'text':entry.summary[i:i+MESSAGE_LEN]})
                result = client.publish(MQTT_TOPIC, payload)
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    print(f"Failed to publish: {result.rc}")
            io += 1
        
        time.sleep(0.1)  # Slower for better readability
        
except KeyboardInterrupt:
    print("\nShutting down...")
finally:
    print("Streaming complete!")
    client.loop_stop()
    client.disconnect()
