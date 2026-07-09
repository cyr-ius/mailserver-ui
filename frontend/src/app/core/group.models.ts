import { Role, User } from './auth.models';

export interface Group {
  id: number;
  name: string;
  description: string;
  /** Role granted to every member of this group. */
  role: Role;
  created_at: string;
  updated_at: string;
}

export interface GroupWithMembers extends Group {
  member_count: number;
}

export interface GroupWithDetails extends Group {
  members: User[];
}
