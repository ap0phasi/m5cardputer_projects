import urllib.request
import feedparser
import paho.mqtt.client as mqtt
import time

# Base api query url
base_url = 'http://export.arxiv.org/api/query?'
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
MQTT_TOPIC = "cardputer/corner/0"

# MQTT callbacks
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT Broker: {MQTT_BROKER}")
    else:
        print(f"Failed to connect, return code {rc}")

client = mqtt.Client()
client.on_connect = on_connect
print(f"Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)

# Search parameters
search_query = 'all:electron'  # search for electron in all fields
start = 0                      # retrieve the first 5 results
max_results = 5

query = 'search_query=%s&start=%i&max_results=%i' % (search_query,
                                                     start,
                                                     max_results)
# perform a GET request using the base_url and query
response = urllib.request.urlopen(base_url + query).read()

# parse the response using feedparser
feed = feedparser.parse(response)

# print out feed information
print('Feed title:', feed.feed.title)
print('Feed entries:', len(feed.entries))
print('\nFirst entry:')
if feed.entries:
    entry = feed.entries[0]
    print('Title:', entry.title)
    print('Published:', entry.published)
    print('Summary:', entry.summary)

MESSAGE_LEN = 50
client.loop_start()  # Start MQTT loop in background

print(f"\nStreaming to MQTT topic: {MQTT_TOPIC}")
print("=" * 50)

while True:
    # Stream the summary in chunks
    for i in range(0, len(entry.summary)-MESSAGE_LEN, 2):
        payload = entry.summary[i:i+MESSAGE_LEN]
        print(payload)
        result = client.publish(MQTT_TOPIC, payload)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"Failed to publish: {result.rc}")
        time.sleep(0.1) # Slower for better readability

print("\nStreaming complete!")
client.loop_stop()
client.disconnect()
