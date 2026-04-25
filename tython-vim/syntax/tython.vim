if exists("b:current_syntax")
  finish
endif

syntax keyword tythonKeyword const var func class record if else return true false none import pyimport
syntax match tythonType /\<\(int\|float\|bool\|str\)\>/
syntax region tythonString start=/"/ end=/"/
syntax match tythonNumber /\v<[0-9]+(\.[0-9]+)?>/

highlight default link tythonKeyword Keyword
highlight default link tythonType Type
highlight default link tythonString String
highlight default link tythonNumber Number

let b:current_syntax = "tython"
