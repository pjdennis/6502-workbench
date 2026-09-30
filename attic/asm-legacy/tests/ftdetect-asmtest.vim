" Vim filetype detection for asmtest files
" Add this to ~/.vim/ftdetect/asmtest.vim

au BufRead,BufNewFile *_tests.txt set filetype=asmtest
au BufRead,BufNewFile *.asmtest set filetype=asmtest
