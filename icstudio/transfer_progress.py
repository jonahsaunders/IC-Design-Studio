"""Progress text shared by package transfers and first-run setup."""
import math
import time


def duration(seconds):
    seconds = max(1, math.ceil(seconds))
    if seconds < 60:
        return f'{seconds} s'
    if seconds < 3600:
        return f'{seconds // 60} min {seconds % 60} s'
    return f'{seconds // 3600} h {(seconds % 3600) // 60} min'


def size(count):
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if count < 1024 or unit == 'GiB':
            return f'{count:.0f} B' if unit == 'B' else f'{count:.1f} {unit}'
        count /= 1024


class ProgressRate:
    def __init__(self):
        self.start = self.updated = time.monotonic()
        self.done = 0

    def describe(self, done, total, unit='bytes'):
        now = time.monotonic()
        if done > self.done:
            self.updated, self.done = now, done
        elapsed = now - self.start
        quantity = size(done) if unit == 'bytes' else str(done)
        if total:
            quantity += ' of ' + (size(total) if unit == 'bytes' else str(total))
        if unit != 'bytes':
            quantity += ' ' + unit
        if total and done >= total:
            return quantity
        if not total:
            estimate = 'Time remaining unknown'
        elif now - self.updated > 15 and unit == 'bytes':
            estimate = 'Waiting for data'
        elif done and elapsed >= 1:
            estimate = 'About ' + duration((total - done) * elapsed / done) + ' left'
        else:
            estimate = 'Estimating time remaining…'
        return quantity + ' · ' + estimate
