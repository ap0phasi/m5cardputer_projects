import urllib.request
import feedparser
import paho.mqtt.client as mqtt
import time
import json


# RSS feed URLs
RSS_FEEDS = {
    'bbc': 'http://feeds.bbci.co.uk/news/rss.xml',
    'hn': 'https://news.ycombinator.com/rss',
    'reddit': 'https://www.reddit.com/.rss'
}

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
current_feed = 'bbc'  # default feed

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
    global requery_flag, current_feed
    if msg.topic == MQTT_QUERY_TOPIC:
        new_feed = msg.payload.decode('utf-8').strip().lower()
        if new_feed in RSS_FEEDS:
            print(f"\nReceived feed change: '{new_feed}'")
            current_feed = new_feed
            requery_flag = True
        else:
            print(f"\nUnknown feed: '{new_feed}'. Available: {list(RSS_FEEDS.keys())}")

def fetch_feed(feed_name):
    """Fetch and parse the RSS feed."""
    feed_url = RSS_FEEDS.get(feed_name, RSS_FEEDS['bbc'])
    print(f"Fetching: {feed_name} ({feed_url})")
    
    try:
        # perform a GET request
        response = urllib.request.urlopen(feed_url, timeout=10).read()
        
        # parse the response using feedparser
        parsed_feed = feedparser.parse(response)
        
        print(f'Feed entries: {len(parsed_feed.entries)}')
        if parsed_feed.entries:
            entry = parsed_feed.entries[0]
            print('First entry:')
            print('Title:', entry.title)
            # Get description/summary
            desc = entry.get('summary', entry.get('description', 'No description'))
            print('Summary:', desc[:100] + '...' if len(desc) > 100 else desc)
        
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
feed = fetch_feed(current_feed)

MESSAGE_LEN = 200
client.loop_start()  # Start MQTT loop in background

io = 0
try:
    while True:
        # Check if we need to requery
        if requery_flag:
            print(f"\nRequerying with: {current_feed}")
            new_feed = fetch_feed(current_feed)
            if new_feed and new_feed.entries:  # Only update if fetch succeeded
                feed = new_feed
                io = 0  # Reset streaming position
            else:
                print("Failed to fetch new feed, keeping existing content")
            requery_flag = False
        
        # Stream the summary in chunks
        if feed and feed.entries:
            for ie, entry in enumerate(feed.entries[:len(MQTT_TOPICS)]):
                MQTT_TOPIC = MQTT_TOPICS[ie]
                # Get description/summary from entry
                desc = entry.get('summary', entry.get('description', 'No description available'))
                entry_words = desc.split(" ")
                i = io % len(entry_words)
                payload = json.dumps({'title':entry.title, 'text':" ".join(entry_words[i:i+MESSAGE_LEN])})
                result = client.publish(MQTT_TOPIC, payload)
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    print(f"Failed to publish: {result.rc}")
            io += 1
        
        time.sleep(0.5)  # Slower for better readability
        
except KeyboardInterrupt:
    print("\nShutting down...")
finally:
    print("Streaming complete!")
    client.loop_stop()
    client.disconnect()
