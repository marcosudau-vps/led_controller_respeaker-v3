"""Studio Lab: the experimental visual editor, as one tab of the studio.

Experimental on purpose. It is a place to try out how designing effects should
feel — layers, blocks, a timeline, stepping through states — on top of the
headless core in :mod:`lefx.effect_creation.visual`, which stays the only
owner of the document and the only thing that computes frames.

Split like the studio itself: ``clock`` and ``output`` carry no Qt and are
tested without a display; ``page``, ``tree``, ``inspector``, ``timeline`` and
``ring`` draw. Each panel talks to the page through a few signals, so one can be
swapped for another experiment without touching the rest.
"""
