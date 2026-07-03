# hermes config YAML List Workaround

## Problem
`hermes config set model.available_models.0 deepseek-v4-pro` creates a **dict** (with string keys "0", "1") instead of a proper YAML list.

Result:
```yaml
available_models:
  '0': deepseek-v4-pro
  '1': deepseek-v4-flash
```

Expected:
```yaml
available_models:
  - deepseek-v4-pro
  - deepseek-v4-flash
```

## Fix
Use Python to read → convert dict to list → write:
```python
import yaml
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)

am = cfg['model'].get('available_models', {})
if isinstance(am, dict):
    cfg['model']['available_models'] = list(am.values())

with open('config.yaml', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
```

## Alternative
If you don't want to use Python, use `hermes config set` with JSON:
```bash
hermes config set model.available_models '["deepseek-v4-pro","deepseek-v4-flash"]'
```
This stores as a JSON string (may or may not be parsed as list).
