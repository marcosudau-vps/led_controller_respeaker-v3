from lefx.sdk import BaseEffect, ColorModel, RenderContext, StateDefinition, StateSlot


class Blackout(BaseEffect):
    """Every LED off, deliberately and opaquely.

    This is not the same as having no state. An empty layer contributes nothing
    and lets whatever sits below it show; this state writes black and covers it.
    The colour model is ``none``, so the definition declares no colour fields at
    all — including brightness, which would have nothing to act on.
    """

    definition = StateDefinition(
        id="blackout",
        title="Blackout",
        description="Switches every LED off while remaining an active state.",
        color_model=ColorModel.NONE,
        slots=(StateSlot.PRIMARY, StateSlot.BACKGROUND),
        restorable=True,
        tags=("core", "state", "utility"),
    )

    def render(self, ctx: RenderContext) -> list[int | None]:
        return ctx.blank_frame()
