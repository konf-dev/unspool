import { describe, it, expect, beforeEach } from 'vitest'
import { useMessageStore } from '@/stores/messageStore'

describe('messageStore', () => {
  beforeEach(() => {
    useMessageStore.setState({
      messages: [],
      streamingContent: '',
      isStreaming: false,
      isThinking: false,
      toolStatus: null,
      pendingActions: null,
      queue: [],
      hasMore: true,
      _abortController: null,
    })
  })

  it('has initial empty state', () => {
    const state = useMessageStore.getState()
    expect(state.messages).toEqual([])
    expect(state.isStreaming).toBe(false)
    expect(state.isThinking).toBe(false)
  })

  it('stopStreaming resets streaming state', () => {
    useMessageStore.setState({ isStreaming: true, isThinking: true, streamingContent: 'test' })
    useMessageStore.getState().stopStreaming()
    expect(useMessageStore.getState().isStreaming).toBe(false)
    expect(useMessageStore.getState().isThinking).toBe(false)
    expect(useMessageStore.getState().streamingContent).toBe('')
  })
})
