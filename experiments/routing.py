#!/usr/bin/env python

import asyncio
import datetime
import time
import zoneinfo

from websockets.asyncio.router import route
from websockets.exceptions import ConnectionClosed
from werkzeug.routing import BaseConverter, Map, Rule, ValidationError


async def clock(websocket, tzinfo):
    """Send the current time in the given timezone every second."""
    loop = asyncio.get_running_loop()
    loop_offset = (loop.time() - time.time()) % 1
    try:
        while True:
            # Sleep until the next second according to the wall clock.
            await asyncio.sleep(1 - (loop.time() - loop_offset) % 1)
            now = datetime.datetime.now(tzinfo).replace(microsecond=0)
            await websocket.send(now.isoformat())
    except ConnectionClosed:
        return


async def alarm(websocket, alarm_at, tzinfo):
    """Send the alarm time in the given timezone when it is reached."""
    alarm_at = alarm_at.replace(tzinfo=tzinfo)
    now = datetime.datetime.now(tz=datetime.timezone.utc)

    try:
        async with asyncio.timeout((alarm_at - now).total_seconds()):
            await websocket.wait_closed()
    except asyncio.TimeoutError:
        try:
            await websocket.send(alarm_at.isoformat())
        except ConnectionClosed:
            return


async def timer(websocket, alarm_after):
    """Send the remaining time until the alarm time every second."""
    alarm_at = datetime.datetime.now(tz=datetime.timezone.utc) + alarm_after
    loop = asyncio.get_running_loop()
    loop_offset = (loop.time() - time.time() + alarm_at.timestamp()) % 1

    try:
        while alarm_after.total_seconds() > 0:
            # Sleep until the next second as a delta to the alarm time.
            await asyncio.sleep(1 - (loop.time() - loop_offset) % 1)
            alarm_after = alarm_at - datetime.datetime.now(tz=datetime.timezone.utc)
            # Round up to the next second.
            alarm_after += datetime.timedelta(
                seconds=1,
                microseconds=-alarm_after.microseconds,
            )
            await websocket.send(format_timedelta(alarm_after))
    except ConnectionClosed:
        return


class ZoneInfoConverter(BaseConverter):
    regex = r"[A-Za-z0-9_/+-]+"

    def to_python(self, value):
        try:
            return zoneinfo.ZoneInfo(value)
        except zoneinfo.ZoneInfoNotFoundError:
            raise ValidationError

    def to_url(self, value):
        return value.key


class DateTimeConverter(BaseConverter):
    regex = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{3})?"

    def to_python(self, value):
        try:
            return datetime.datetime.fromisoformat(value)
        except ValueError:
            raise ValidationError

    def to_url(self, value):
        return value.isoformat()


class TimeDeltaConverter(BaseConverter):
    regex = r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{3}(?:[0-9]{3})?)?"

    def to_python(self, value):
        return datetime.timedelta(
            hours=int(value[0:2]),
            minutes=int(value[3:5]),
            seconds=int(value[6:8]),
            milliseconds=int(value[9:12]) if len(value) == 12 else 0,
            microseconds=int(value[9:15]) if len(value) == 15 else 0,
        )

    def to_url(self, value):
        return format_timedelta(value)


def format_timedelta(delta):
    assert 0 <= delta.seconds < 86400
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    seconds = delta.seconds % 60
    if delta.microseconds:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{delta.microseconds:06d}"
    else:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


url_map = Map(
    [
        Rule(
            "/",
            redirect_to="/clock",
        ),
        Rule(
            "/clock",
            defaults={"tzinfo": datetime.timezone.utc},
            endpoint=clock,
        ),
        Rule(
            "/clock/<tzinfo:tzinfo>",
            endpoint=clock,
        ),
        Rule(
            "/alarm/<datetime:alarm_at>/<tzinfo:tzinfo>",
            endpoint=alarm,
        ),
        Rule(
            "/timer/<timedelta:alarm_after>",
            endpoint=timer,
        ),
    ],
    converters={
        "tzinfo": ZoneInfoConverter,
        "datetime": DateTimeConverter,
        "timedelta": TimeDeltaConverter,
    },
)


async def main():
    async with route(url_map, "localhost", 8888) as server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
