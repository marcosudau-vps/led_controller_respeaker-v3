"""Makes ``python -m respeaker_led.simulator`` work.

Running ``app.py`` as a plain file cannot work: the module reaches its siblings
with relative imports, and a file executed by path has no package to be relative
to. Running it as a module gives it one — so this is the form to reach for when
the console script is not on PATH, which is most of the time during development.

    python -m respeaker_led.simulator --port 8787
"""

from __future__ import annotations

from .app import main

raise SystemExit(main())
