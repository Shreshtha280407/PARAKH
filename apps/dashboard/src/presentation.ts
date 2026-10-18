export function humanize(value: string) {
  const text = value.toLowerCase().replaceAll('_', ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function qualificationName(code: string, name?: string) {
  return name || (code.startsWith('CON/Q0602') ? 'Assistant Electrician' : 'Qualification pack');
}

export function readableTaskTitle(title: string) {
  return title.replace(/\bLV\b/g, 'low-voltage').replace(' / fault', ' and fault finding').replace(' & ', ' and ');
}

