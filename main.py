import os
import sys

os.environ["GEVENT_PURE_PYTHON"] = "1"

from app import main

if __name__ == "__main__":
    main()