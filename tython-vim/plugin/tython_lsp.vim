if exists('g:loaded_tython_lsp')
  finish
endif
let g:loaded_tython_lsp = 1

let s:server_registered = 0

function! s:RegisterTythonLsp() abort
  if s:server_registered
    return
  endif
  if !exists('*LspAddServer')
    silent! packadd lsp
  endif
  if !exists('*LspAddServer')
    return
  endif

  let l:cmd = get(g:, 'tython_lsp_cmd', [])
  if empty(l:cmd)
    let l:pyproject = findfile('pyproject.toml', expand('<sfile>:p:h') . ';')
    if !empty(l:pyproject) && executable('uv')
      let l:cmd = ['uv', 'run', '--directory', fnamemodify(l:pyproject, ':h'), 'tython-lsp']
    elseif executable('tython')
      let l:cmd = ['tython', 'lsp', 'start']
    elseif executable('tython-lsp')
      let l:cmd = ['tython-lsp']
    else
      let l:cmd = ['uv', 'run', 'tython-lsp']
    endif
  endif

  call LspAddServer([#{
        \ name: 'tython-lsp',
        \ filetype: ['tython'],
        \ path: l:cmd[0],
        \ args: l:cmd[1:],
        \ traceLevel: 'debug'
        \ }])
  let s:server_registered = 1
endfunction

augroup tython_lsp
  autocmd!
  autocmd BufRead,BufNewFile *.ty setfiletype tython
  autocmd VimEnter * call <SID>RegisterTythonLsp()
  autocmd FileType tython call <SID>RegisterTythonLsp()
  autocmd FileType tython if exists(':LspHover') | setlocal keywordprg=:LspHover | nnoremap <buffer> K :LspHover<CR> | endif
  autocmd FileType tython if exists(':LspDiag') | nnoremap <buffer> <leader>e :LspDiag current<CR> | endif
augroup END
