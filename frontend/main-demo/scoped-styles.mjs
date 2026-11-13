/** Закрытая сборка CSS двух проверенных renderer; не обработчик произвольного CSS. */
export function scopedStyles(source,scope){
  if(!['.main-demo-catalog','.main-demo-documents'].includes(scope)||typeof source!=='string')throw Error('Unknown renderer style scope');
  // Global registrations/imports cannot be contained by @scope.
  for(const match of source.matchAll(/@([a-z-]+)/gi))if(!['media','supports','container'].includes(match[1].toLowerCase()))throw Error('Unscoped CSS at-rule');
  if(/url\s*\(|:host|:global/i.test(source))throw Error('Unscoped CSS resource or selector');
  const mapped=source.replace(/:root\b/g,':scope').replace(/(^|[{}]\s*)(?:html|body)(?=\s*\{)/g,'$1:scope');
  if(/:root\b|(^|[^A-Za-z0-9_-])(?:html|body)(?=$|[^A-Za-z0-9_-])/m.test(mapped))throw Error('Unsupported document selector');
  return `@scope (${scope}) {\n${mapped}\n}\n`;
}
