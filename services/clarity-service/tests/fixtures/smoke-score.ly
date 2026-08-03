\version "2.24.1"

\header {
  title = "ScoreMosaic Runtime Check"
  tagline = ##f
}

\paper {
  #(set-paper-size "a4")
  top-margin = 12\mm
  bottom-margin = 12\mm
  left-margin = 14\mm
  right-margin = 14\mm
}

music = \relative c' {
  \clef treble
  \key c \major
  \time 4/4
  c4 d e f |
  g4 a b c |
  c4 b a g |
  f4 e d c |
  \bar "|."
}

\score {
  \new Staff \music
  \layout { }
}
