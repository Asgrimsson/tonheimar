# Tónheimar v3.1 - set_current autoplay lagað

## Lagað í v3.1

Lagaði villuna:

`TypeError: set_current() got an unexpected keyword argument 'autoplay'`

Ástæða:
- Minningarvélin og Radio Auðbert kölluðu á:
  `set_current(idx, autoplay=True)`
- en `set_current()` tók ekki við `autoplay` í þessari útgáfu.

Lausn:
- `set_current(idx, autoplay=False)` er nú sveigjanlegt.
- Radio Auðbert og Minningarvélin ættu að ræsa án villu.
- Lukkudýralínur uppfærast þegar lag er valið.

## Keyra

```bash
py -m pip install --upgrade -r requirements.txt
py -m streamlit run app.py
```
