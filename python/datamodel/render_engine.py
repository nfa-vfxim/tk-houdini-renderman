from enum import Enum


class RenderEngine(str, Enum):
    RENDERMAN = "RenderMan"
    KARMA = "Karma"
