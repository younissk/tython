local function default_cmd()
  if vim.fn.executable('tython') == 1 then
    return { 'tython', 'lsp', 'start' }
  end
  if vim.fn.executable('tython-lsp') == 1 then
    return { 'tython-lsp' }
  end
  return { 'uv', 'run', 'tython-lsp' }
end

local cmd = vim.g.tython_lsp_cmd
if type(cmd) ~= 'table' or vim.tbl_isempty(cmd) then
  cmd = default_cmd()
end

return {
  name = 'tython-lsp',
  cmd = cmd,
  filetypes = { 'tython' },
  root_markers = { 'project.toml', '.git' },
}
