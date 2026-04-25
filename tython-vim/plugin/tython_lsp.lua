if vim.g.loaded_tython_nvim_lsp then
  return
end
vim.g.loaded_tython_nvim_lsp = 1

if not vim.lsp or not vim.lsp.enable then
  return
end

vim.lsp.enable('tython')
