/**
 * A simple typed event emitter that can be extended by other classes
 */
export class EventEmitter<
  EventType extends string,
  EventPayloadMap = Record<EventType, any>
> {
  private listeners: Map<EventType | string, Function[]> = new Map();

  /**
   * Register an event handler for a specific event
   * 
   * @param event - The event to listen for
   * @param listener - The callback function
   */
  on<E extends EventType>(
    event: E, 
    listener: (data: EventPayloadMap extends Record<E, infer P> ? P : any) => void
  ): void {
    const listeners = this.listeners.get(event) || [];
    listeners.push(listener);
    this.listeners.set(event, listeners);
  }

  /**
   * Register a one-time event handler for a specific event
   * 
   * @param event - The event to listen for
   * @param listener - The callback function
   */
  once<E extends EventType>(
    event: E, 
    listener: (data: EventPayloadMap extends Record<E, infer P> ? P : any) => void
  ): void {
    const onceWrapper = (data: any) => {
      listener(data);
      this.off(event, onceWrapper);
    };
    this.on(event, onceWrapper);
  }

  /**
   * Remove an event handler
   * 
   * @param event - The event to remove the listener from
   * @param listener - The callback function to remove
   */
  off(event: EventType | string, listener: Function): void {
    const listeners = this.listeners.get(event);
    if (!listeners) return;
    
    const index = listeners.indexOf(listener);
    if (index !== -1) {
      listeners.splice(index, 1);
      if (listeners.length === 0) {
        this.listeners.delete(event);
      } else {
        this.listeners.set(event, listeners);
      }
    }
  }

  /**
   * Emit an event with data
   * 
   * @param event - The event to emit
   * @param data - The data to pass to the event handlers
   */
  emit<E extends EventType>(
    event: E, 
    data?: EventPayloadMap extends Record<E, infer P> ? P : any
  ): void {
    const listeners = this.listeners.get(event);
    if (listeners) {
      listeners.forEach(listener => {
        try {
          listener(data);
        } catch (error) {
          console.error(`Error in event listener for ${String(event)}:`, error);
        }
      });
    }
  }

  /**
   * Remove all listeners
   * 
   * @param event - Optional event to remove all listeners for
   */
  removeAllListeners(event?: EventType | string): void {
    if (event) {
      this.listeners.delete(event);
    } else {
      this.listeners.clear();
    }
  }

  /**
   * Get the number of listeners for an event
   * 
   * @param event - The event to get listener count for
   * @returns The number of listeners
   */
  listenerCount(event: EventType | string): number {
    const listeners = this.listeners.get(event);
    return listeners ? listeners.length : 0;
  }
} 