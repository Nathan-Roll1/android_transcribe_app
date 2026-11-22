import re
import sys
from xml.etree import ElementTree

try:
    tree = ElementTree.parse(sys.argv[1])
except ElementTree.ParseError:
    sys.exit(1)
items = {node.get("resource-id", "").split("/")[-1]: node.get("text") or "" for node in tree.iter("node")}
print({key: items.get(key) for key in ("txt_status", "txt_result")})
actual = re.findall(r"[a-z]+", items.get("txt_result", "").lower())
expected = "and so my fellow americans ask not what your country can do for you ask what you can do for your country".split()
sys.exit(0 if actual == expected else 1)
