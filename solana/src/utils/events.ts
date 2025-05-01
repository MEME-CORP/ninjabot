import { EventEmitter } from 'events';

/**
 * Event types that can be emitted during execution
 */
export enum EventType {
  // Run lifecycle events
  RUN_STARTED = 'RunStarted',
  RUN_FINISHED = 'RunFinished',
  RUN_ERROR = 'RunError',
  
  // Wallet events
  WALLET_CREATED = 'WalletCreated',
  
  // Schedule events
  SCHEDULE_GENERATED = 'ScheduleGenerated',
  FUNDING_CHILDREN = 'FundingChildren',
  
  // Transaction events
  TRANSFER_ATTEMPT = 'TransferAttempt',
  TX_SENT = 'TxSent',
  TX_CONFIRMED = 'TxConfirmed',
  TX_FAILED = 'TxFailed',
  FEE_SPIKE_DETECTED = 'FeeSpikeDetected',
  RETRY_ATTEMPT = 'RetryAttempt'
}

/**
 * Base event interface that all events extend
 */
export interface BaseEvent {
  type: EventType;
  timestamp: number; // Unix timestamp
}

/**
 * Run lifecycle events
 */
export interface RunStartedEvent extends BaseEvent {
  type: EventType.RUN_STARTED;
  params: {
    networkType: 'devnet' | 'mainnet';
    childWalletsCount: number;
    totalVolume: string; // BigInt serialized as string
    tokenMint: string;
    tokenDecimals: number;
  };
}

export interface RunFinishedEvent extends BaseEvent {
  type: EventType.RUN_FINISHED;
  status: 'completed' | 'failed' | 'partial';
  summary: {
    totalTransfers: number;
    successfulTransfers: number;
    failedTransfers: number;
    feeSpikeSkips: number;
    totalFeesCollected: string; // BigInt serialized as string
  };
}

export interface RunErrorEvent extends BaseEvent {
  type: EventType.RUN_ERROR;
  error: string;
  stack?: string;
}

/**
 * Wallet events
 */
export interface WalletCreatedEvent extends BaseEvent {
  type: EventType.WALLET_CREATED;
  walletType: 'mother' | 'child';
  index?: number; // For child wallets
  address: string;
}

/**
 * Schedule events
 */
export interface ScheduleGeneratedEvent extends BaseEvent {
  type: EventType.SCHEDULE_GENERATED;
  operationsCount: number;
  totalAmount: string; // BigInt serialized as string
  totalFees: string; // BigInt serialized as string
}

export interface FundingChildrenEvent extends BaseEvent {
  type: EventType.FUNDING_CHILDREN;
  childCount: number;
  amountPerChild: string; // BigInt serialized as string
}

/**
 * Transaction events
 */
export interface TransferAttemptEvent extends BaseEvent {
  type: EventType.TRANSFER_ATTEMPT;
  opIndex: number;
  sourceIndex: number;
  destinationAddress: string;
  amount: string; // BigInt serialized as string
  isFee: boolean;
}

export interface TxSentEvent extends BaseEvent {
  type: EventType.TX_SENT;
  opIndex: number;
  signature: string;
}

export interface TxConfirmedEvent extends BaseEvent {
  type: EventType.TX_CONFIRMED;
  opIndex: number;
  signature: string;
  slot?: number;
}

export interface TxFailedEvent extends BaseEvent {
  type: EventType.TX_FAILED;
  opIndex: number;
  signature?: string;
  error: string;
  details?: any;
}

export interface FeeSpikeDetectedEvent extends BaseEvent {
  type: EventType.FEE_SPIKE_DETECTED;
  opIndex: number;
  currentFee: string; // BigInt serialized as string
  thresholdFee: string; // BigInt serialized as string
}

export interface RetryAttemptEvent extends BaseEvent {
  type: EventType.RETRY_ATTEMPT;
  opIndex: number;
  attempt: number;
  previousSignature?: string;
  reason: string;
}

/**
 * Union type of all possible events
 */
export type NinjaBotEvent =
  | RunStartedEvent
  | RunFinishedEvent
  | RunErrorEvent
  | WalletCreatedEvent
  | ScheduleGeneratedEvent
  | FundingChildrenEvent
  | TransferAttemptEvent
  | TxSentEvent
  | TxConfirmedEvent
  | TxFailedEvent
  | FeeSpikeDetectedEvent
  | RetryAttemptEvent;

/**
 * Event queue for managing and distributing events
 */
export class EventQueue {
  private emitter = new EventEmitter();
  
  /**
   * Emit an event to all subscribers
   */
  emit(event: NinjaBotEvent): void {
    this.emitter.emit(event.type, event);
    // Also emit to 'all' channel so subscribers can listen to all events
    this.emitter.emit('all', event);
  }
  
  /**
   * Subscribe to a specific event type
   */
  on(eventType: EventType | 'all', listener: (event: NinjaBotEvent) => void): void {
    this.emitter.on(eventType, listener);
  }
  
  /**
   * Subscribe to a specific event type once
   */
  once(eventType: EventType | 'all', listener: (event: NinjaBotEvent) => void): void {
    this.emitter.once(eventType, listener);
  }
  
  /**
   * Unsubscribe from a specific event type
   */
  off(eventType: EventType | 'all', listener: (event: NinjaBotEvent) => void): void {
    this.emitter.off(eventType, listener);
  }
  
  /**
   * Helper to create events with timestamp automatically set
   */
  createEvent<T extends NinjaBotEvent>(event: Omit<T, 'timestamp'>): T {
    return {
      ...event,
      timestamp: Date.now(),
    } as T;
  }
} 