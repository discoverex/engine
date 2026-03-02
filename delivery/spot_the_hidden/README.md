# spot_the_hidden delivery package

이 패키지는 엔진(`discoverex`) 출력 Scene JSON을
숨은그림찾기 서비스 전달용 번들(`spot_hidden_bundle.json`)로 변환합니다.

- 메인 패키지(`src/discoverex`)에 포함되지 않는 외부 후처리 계층입니다.
- 번들에는 `playable` + `answer_key` + `delivery_meta`가 포함됩니다.
- 프런트에는 `playable`만 노출하고 `answer_key`는 서버 내부에서만 사용해야 합니다.

실행 예시:

```bash
python -m delivery.spot_the_hidden.cli \
  --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json
```
