from dataclasses import dataclass

from .render_engine import RenderEngine


@dataclass
class LPEControl:
    renderer: RenderEngine
    lop_control: str
    lop_light_group: str
    sop_light_group: str

    def get_control(self) -> str:
        return self.lop_control

    def get_light_group(self, is_lop: bool = False) -> str:
        return self.lop_light_group if is_lop else self.sop_light_group
