local function checkout_root()
  local source = debug.getinfo(1, 'S').source
  if type(source) ~= 'string' or source:sub(1, 1) ~= '@' then
    return nil
  end

  local plugin_file = source:sub(2)
  local pyproject = vim.fs.find('pyproject.toml', {
    path = vim.fs.dirname(plugin_file),
    upward = true,
  })[1]
  if pyproject == nil then
    return nil
  end
  return vim.fs.dirname(pyproject)
end

local function default_cmd()
  local repo_root = checkout_root()
  if repo_root ~= nil and vim.fn.executable('uv') == 1 then
    return { 'uv', 'run', '--directory', repo_root, 'tython-lsp' }
  end
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
