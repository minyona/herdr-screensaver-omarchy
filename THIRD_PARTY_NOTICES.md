# Third-party notices

## Omarchy

`bin/herdr-screensaver-launch` is derived from Omarchy 4.0.0.alpha's `bin/omarchy-launch-screensaver`
(only the terminal lines differ: they run this plugin's `lib/session.sh`, titled `herdr-screensaver`, at a
font size fit to each monitor; the "already running" check looks for a screensaver terminal; the ttfx check
is gone). `lib/session.sh` follows Omarchy's `bin/omarchy-screensaver` (cursor hiding, the resize wait,
ending on focus loss, closing the windows with `pkill -f '[o]rg.omarchy.screensaver'`).
`Model.secondsFromConfig` is Omarchy's `IdleModel.secondsFromConfig`, and the default idle times (150 s
screensaver, 300 s lock) are Omarchy's.

Omarchy: https://github.com/basecamp/omarchy

```
MIT License

Copyright (c) David Heinemeier Hansson

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
