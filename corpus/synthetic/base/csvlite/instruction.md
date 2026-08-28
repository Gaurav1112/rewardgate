# Quoted fields containing the delimiter are split incorrectly

Reading a row where a quoted field contains a comma returns too many fields.

```python
>>> from csvlite import parse_row
>>> parse_row('a,"b,c"')
['a', '"b', 'c"']
```

Expected two fields, `a` and `b,c`. The quotes should be consumed and the comma inside them should
not act as a delimiter.

Rows without quoted fields must keep their current behaviour.
