import os

from metaflow.cards import MetaflowCard


class SpareCoresCard(MetaflowCard):
    type = "spare_cores"
    RUNTIME_UPDATABLE = True

    def render(self, task):
        return f"card pid: {os.getpid()}"


CARDS = [SpareCoresCard]
