import pytz
from datetime import UTC, datetime
from timefhuman import timefhuman, tfhConfig, Direction

config = tfhConfig(
)

query_text = 'last month'
out = timefhuman(query_text, config = config)
print(out)