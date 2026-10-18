#!/usr/bin/env python3
"""Return a Scholar publication snapshot; caller enforces a hard timeout."""

import json

from scholarly import scholarly

PROFILE_ID = "jQBiItMAAAAJ"

author = scholarly.search_author_id(PROFILE_ID)
author = scholarly.fill(author, sections=["publications"])
print(json.dumps(author.get("publications", []), ensure_ascii=False, default=str))
