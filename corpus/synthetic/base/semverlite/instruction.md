# Pre-release versions compare equal to their release

Comparing a pre-release version against its own release reports that they are the same version.

```python
>>> from semverlite import compare
>>> compare("1.0.0-alpha", "1.0.0")
0
```

Semantic versioning states that a pre-release version has lower precedence than the associated
normal version, so this should report that `1.0.0-alpha` comes first.

Two pre-releases of the same version should also order against each other, and versions without a
pre-release suffix must keep their current behaviour.
