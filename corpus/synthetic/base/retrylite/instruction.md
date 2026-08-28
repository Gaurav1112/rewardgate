# Backoff delay grows without bound

The retry delay keeps doubling on every attempt, so a long-running retry loop eventually schedules
a wait of hours.

```python
>>> from retrylite import backoff_delay
>>> backoff_delay(20)
524288.0
```

The module documents a maximum delay of 60 seconds, and the delay should stop growing once it
reaches that ceiling.

Early attempts must keep their current doubling behaviour, and an attempt number below 1 should
still raise `ValueError`.
