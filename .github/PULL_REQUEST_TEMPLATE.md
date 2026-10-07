## Summary

<!-- What does this change and why? Link related issues: Fixes #123 -->

## Type of change

- [ ] Bug fix
- [ ] New feature / option
- [ ] New adapter
- [ ] Docs / examples only
- [ ] Refactor (no behaviour change)

## Checklist

- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] `mypy` passes
- [ ] `pytest` passes, with tests for new behaviour
- [ ] Golden files updated if output changed (`UPDATE_GOLDEN=1 pytest tests/test_golden.py`) and the diff reviewed
- [ ] Examples regenerated if output changed (`agent sync` in `examples/*`)
- [ ] Adapter `version` bumped if its generated output changed
- [ ] README / docs updated if user-facing behaviour changed
