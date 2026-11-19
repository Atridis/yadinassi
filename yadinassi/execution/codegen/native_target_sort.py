"""Deterministic sort model for the explicit linux-8.3.27.1508 target.

This independently written introsort model matches the measured ValueTable
orders on Linux amd64 8.3.27.1508, ru_RU. Those observations cover 15..18 rows
and the original locale checkpoints, not arbitrary input sizes or native
implementation internals. It is neither host std::sort nor a universal Linux
rule. Keys, accepted values, resource limits and atomic commit belong to the
caller; this module only reorders a private list using a strict-less predicate.

Median-of-three partitioning stops at 16 items. A logarithmic partition-depth
budget switches to heapsort; insertion sorting finishes the small partitions.
The worst-case comparison bound is O(n log n), with O(log n) control storage.
Pivot and heap tie choices are intentional parts of this empirical model.
"""

_INSERTION_LIMIT = 16


def _partition(items, start, stop, less):
    """Place a sampled median at start, then partition with strict scans."""
    low, high = start + 1, (start + stop) // 2
    if not less(items[low], items[high]):
        low, high = high, low
    end = stop - 1
    if less(items[high], items[end]):
        median = high
    elif less(items[low], items[end]):
        median = end
    else:
        median = low
    items[start], items[median] = items[median], items[start]
    pivot = items[start]
    left, right = start + 1, stop
    while True:
        # The sampled values bound the scans, including all-equal inputs.
        while less(items[left], pivot):
            left += 1
        right -= 1
        while less(pivot, items[right]):
            right -= 1
        if left >= right:
            return left
        items[left], items[right] = items[right], items[left]
        left += 1


def _heap_sort(items, start, stop, less):
    """Sort a half-open span, preferring the right child when keys tie."""
    count = stop - start

    def sift(root, value, size):
        # Move a hole down to a leaf, then place value on its path upwards.
        # This avoids exchanging a value at every level of the heap.
        hole = root
        while 2 * hole + 1 < size:
            child = 2 * hole + 1
            if child + 1 < size and not less(items[start + child + 1],
                                            items[start + child]):
                child += 1
            items[start + hole] = items[start + child]
            hole = child
        while hole > root:
            parent = (hole - 1) // 2
            if not less(items[start + parent], value):
                break
            items[start + hole] = items[start + parent]
            hole = parent
        items[start + hole] = value

    for root in range(count // 2 - 1, -1, -1):
        sift(root, items[start + root], count)
    for size in range(count - 1, 0, -1):
        value = items[start + size]
        items[start + size] = items[start]
        sift(0, value, size)


def introsort(items, less):
    """Sort a private list in place; equal keys deliberately need not be stable."""
    count = len(items)
    if count < 2:
        return
    pending = [(0, count, 2 * (count.bit_length() - 1))]
    while pending:
        start, stop, depth = pending.pop()
        while stop - start > _INSERTION_LIMIT:
            if depth == 0:
                _heap_sort(items, start, stop, less)
                break
            depth -= 1
            split = _partition(items, start, stop, less)
            pending.append((start, split, depth))
            start = split

    # Partition boundaries are ordered. Only small, bounded spans remain
    # unsorted, so this final insertion pass takes O(n * _INSERTION_LIMIT).
    # Strict shifts keep the current order of ties, not the original order.
    for index in range(1, count):
        value = items[index]
        hole = index
        while hole and less(value, items[hole - 1]):
            items[hole] = items[hole - 1]
            hole -= 1
        items[hole] = value
