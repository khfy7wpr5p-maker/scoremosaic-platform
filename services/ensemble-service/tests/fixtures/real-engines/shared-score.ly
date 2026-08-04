\version "2.24.1"

\paper {
  indent = 0\mm
  ragged-last = ##f
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
