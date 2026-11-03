/** One line for what a streamed turn is doing now (llm/utils/sse.py frames). */
export function describeProgress(frame) {
  if (!frame) return 'Thinking…';
  const { event, data } = frame;
  switch (event) {
    case 'start':
      return 'Thinking…';
    case 'iteration':
      return data?.iteration > 1 ? 'Thinking about the results…' : 'Thinking…';
    case 'tool_start':
      return `Using ${humanise(data?.name)}…`;
    case 'tool_result':
      return data?.ok === false
        ? `${capitalise(humanise(data?.name))} failed; working around it…`
        : `Read ${humanise(data?.name)}`;
    case 'finalising':
      return 'Writing the answer…';
    default:
      return 'Working…';
  }
}

const humanise = (name) => (name ? String(name).replace(/_/g, ' ') : 'a tool');
const capitalise = (text) => text.charAt(0).toUpperCase() + text.slice(1);
