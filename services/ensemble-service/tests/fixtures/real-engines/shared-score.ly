\version "2.24.1"

\paper {
  paper-width = 180\mm
  paper-height = 55\mm
  top-margin = 5\mm
  bottom-margin = 5\mm
  left-margin = 5\mm
  right-margin = 5\mm
  indent = 0\mm
  ragged-last = ##f
  ragged-last-bottom = ##f
  tagline = ##f
}

\layout { }

\relative c' {
  \clef treble
  \key c \major
  \time 4/4
  c4 d e f |
  g4 a b c |
  c4 b a g |
  f4 e d c |
  \bar "|."
}
