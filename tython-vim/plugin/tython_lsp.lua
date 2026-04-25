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

local group = vim.api.nvim_create_augroup('tython_nvim_lsp', { clear = true })

vim.api.nvim_create_autocmd('FileType', {
  group = group,
  pattern = 'tython',
  callback = enable_tython,
})

vim.api.nvim_create_autocmd('LspAttach', {
  group = group,
  callback = function(args)
    local client = vim.lsp.get_client_by_id(args.data.client_id)
    if not client or client.name ~= 'tython' then
      return
    end

    vim.api.nvim_create_autocmd('BufWritePre', {
      group = group,
      buffer = args.buf,
      callback = function()
        vim.lsp.buf.format({
          async = false,
          timeout_ms = 5000,
          filter = function(format_client)
            return format_client.name == 'tython'
          end,
        })
      end,
    })
  end,
})

vim.schedule(enable_tython)
