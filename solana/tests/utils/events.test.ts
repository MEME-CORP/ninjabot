import { EventQueue, EventType, RunStartedEvent, RunErrorEvent, TxSentEvent } from '../../src/utils/events';
import { jest } from '@jest/globals';

describe('EventQueue', () => {
  let eventQueue: EventQueue;
  
  beforeEach(() => {
    eventQueue = new EventQueue();
  });
  
  test('should emit events to subscribers', () => {
    // Create mock listeners
    const runStartedListener = jest.fn();
    const allEventsListener = jest.fn();
    
    // Subscribe to events
    eventQueue.on(EventType.RUN_STARTED, runStartedListener);
    eventQueue.on('all', allEventsListener);
    
    // Create and emit event
    const event = eventQueue.createEvent<RunStartedEvent>({
      type: EventType.RUN_STARTED,
      params: {
        networkType: 'devnet',
        childWalletsCount: 5,
        totalVolume: '1000000000',
        tokenMint: 'TokenMintAddress',
        tokenDecimals: 9
      }
    });
    
    eventQueue.emit(event);
    
    // Verify listeners were called
    expect(runStartedListener).toHaveBeenCalledWith(event);
    expect(allEventsListener).toHaveBeenCalledWith(event);
  });
  
  test('should not call listeners for other event types', () => {
    // Create mock listeners
    const runStartedListener = jest.fn();
    const runFinishedListener = jest.fn();
    
    // Subscribe to events
    eventQueue.on(EventType.RUN_STARTED, runStartedListener);
    eventQueue.on(EventType.RUN_FINISHED, runFinishedListener);
    
    // Create and emit event
    const event = eventQueue.createEvent<RunErrorEvent>({
      type: EventType.RUN_ERROR,
      error: 'Test error'
    });
    
    eventQueue.emit(event);
    
    // Verify listeners were not called
    expect(runStartedListener).not.toHaveBeenCalled();
    expect(runFinishedListener).not.toHaveBeenCalled();
  });
  
  test('should unsubscribe listeners', () => {
    // Create mock listener
    const listener = jest.fn();
    
    // Subscribe and then unsubscribe
    eventQueue.on(EventType.RUN_STARTED, listener);
    eventQueue.off(EventType.RUN_STARTED, listener);
    
    // Create and emit event
    const event = eventQueue.createEvent<RunStartedEvent>({
      type: EventType.RUN_STARTED,
      params: {
        networkType: 'devnet',
        childWalletsCount: 5,
        totalVolume: '1000000000',
        tokenMint: 'TokenMintAddress',
        tokenDecimals: 9
      }
    });
    
    eventQueue.emit(event);
    
    // Verify listener was not called
    expect(listener).not.toHaveBeenCalled();
  });
  
  test('once should only call listener one time', () => {
    // Create mock listener
    const listener = jest.fn();
    
    // Subscribe with once
    eventQueue.once(EventType.TX_SENT, listener);
    
    // Create and emit event twice
    const event1 = eventQueue.createEvent<TxSentEvent>({
      type: EventType.TX_SENT,
      opIndex: 0,
      signature: 'signature1'
    });
    
    const event2 = eventQueue.createEvent<TxSentEvent>({
      type: EventType.TX_SENT,
      opIndex: 1,
      signature: 'signature2'
    });
    
    eventQueue.emit(event1);
    eventQueue.emit(event2);
    
    // Verify listener was called only once with first event
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith(event1);
  });
  
  test('createEvent should add timestamp', () => {
    // Mock Date.now
    const mockNow = 1619712000000; // May 1, 2021 00:00:00 GMT
    jest.spyOn(Date, 'now').mockImplementation(() => mockNow);
    
    const event = eventQueue.createEvent<RunErrorEvent>({
      type: EventType.RUN_ERROR,
      error: 'Test error'
    });
    
    expect(event.timestamp).toBe(mockNow);
    
    // Restore Date.now
    jest.restoreAllMocks();
  });
}); 