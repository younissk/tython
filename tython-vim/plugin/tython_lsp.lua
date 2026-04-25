if vim.g.loaded_tython_nvim_lsp then
  return
end
vim.g.loaded_tython_nvim_lsp = 1

if not vim.lsp or not vim.lsp.enable then
  return
end

local function enable_tython()
  vim.lsp.enable('tython')
end

vim.api.nvim_create_autocmd('FileType', {
  pattern = 'tython',
  callback = enable_tython,
})

vim.schedule(enable_tython)
