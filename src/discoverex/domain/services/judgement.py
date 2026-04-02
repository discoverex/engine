from __future__ import annotations

from discoverex.domain.scene import Scene, SceneStatus


def judge_scene(scene: Scene) -> SceneStatus:
    return (
        SceneStatus.APPROVED if scene.verification.final.pass_ else SceneStatus.FAILED
    )
