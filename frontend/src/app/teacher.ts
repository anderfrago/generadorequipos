import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api } from './api';

interface ClassInfo {id: string; name: string; academic_year: string; evaluation_period: string; total: number; code: string}
interface Student {id: string; name: string; email: string; status: string; link_active: boolean; result: any; observation: any; conditions: string[]; open_response: string}
interface Detail {classInfo: ClassInfo; students: Student[]; relations: any[]; teachers: any[]}

@Component({selector: 'app-teacher', imports: [FormsModule], templateUrl: './teacher.html'})
export class TeacherPage {
  componentLabels = [{key:'profiles',label:'Perfiles'},{key:'functional',label:'Funcionamiento pr?ctico'},{key:'complementarity',label:'Complementariedad'},{key:'conditions',label:'Condiciones de trabajo'},{key:'relations',label:'Relaciones docentes'}];
  api = inject(Api); classes = signal<ClassInfo[]>([]); detail = signal<Detail | null>(null);
  error = signal(''); message = signal(''); busy = signal(false); selected = signal<Student | null>(null);
  proposal = signal<any>(null); history = signal<any[]>([]); options = signal<any[]>([]); links = signal<{name: string; url: string}[]>([]);
  tab = signal('students'); users = signal<any[]>([]);
  newClass = {name: '', academic_year: '2026-2027', evaluation_period: 'INICIAL'};
  roster = ''; relation = {student_a: '', student_b: '', type: 'NO_JUNTAR', comment: ''}; teacherEmail = '';
  editingUser = signal<string | null>(null); deletingUser = signal<any>(null);
  invitationPreview = signal<any>(null); invitationProgress = signal(''); resendTarget = signal<any>(null);
  mailStatus: Record<string,string> = {PENDING:'Pendiente',STALE:'Enlace actualizado',SENDING:'En curso',SENT:'Aceptado por el servidor',FAILED:'Fallido',UNKNOWN:'Sin confirmación'};
  newUser = {email: '', name: '', role: 'TEACHER', active: true}; sizes = ''; studentA = ''; studentB = ''; toTeam = 0; deletion = '';
  constructor() { if(this.api.user()) void this.run(async () => {await this.loadClasses();}); }
  async run(fn: () => Promise<void>) { if(this.busy()) return; this.busy.set(true); this.error.set(''); this.message.set(''); try { await fn(); } catch(e) {this.error.set((e as Error).message);} finally {this.busy.set(false);} }
  async loadClasses() {this.classes.set(await this.api.request<ClassInfo[]>('/classes'));}
  async refresh() {const id = this.detail()?.classInfo.id; if(id) {this.detail.set(await this.api.request<Detail>('/classes/' + id));if(this.invitationPreview())this.invitationPreview.set(await this.api.request('/classes/'+id+'/invitations'));}}
  open(c: ClassInfo) {void this.run(async () => {this.invitationPreview.set(null);this.resendTarget.set(null);this.detail.set(await this.api.request<Detail>('/classes/' + c.id)); this.proposal.set(null); this.selected.set(null); this.links.set([]); this.tab.set('students'); this.history.set(await this.api.request<any[]>('/classes/'+c.id+'/proposals'));});}
  create() {void this.run(async () => {await this.api.request('/classes','POST',this.newClass); this.newClass.name=''; await this.loadClasses(); this.message.set('Clase creada.');});}
  addStudents() {void this.run(async () => {const students=this.roster.split('\n').filter(x=>x.trim()).map(line=>{const [name,email='']=line.split(/[;\t]/); return {name:name.trim(),email:email.trim()};}); await this.api.request('/classes/'+this.detail()!.classInfo.id+'/students','POST',{students}); this.roster=''; await this.refresh(); this.message.set('Alumnado incorporado.');});}
  link(student: Student, action='current') {void this.run(async () => {const result=await this.api.request<{url?:string}>(this.studentPath(student)+'/link','POST',{action}); if(result.url) this.links.set([{name:student.name,url:result.url}]); else this.links.set([]); await this.refresh();});}
  allLinks() {void this.run(async () => {const results=[]; for(const student of this.detail()!.students) {const data=await this.api.request<{url:string}>(this.studentPath(student)+'/link','POST',{}); results.push({name:student.name,url:data.url});} this.links.set(results); await this.refresh();});}
  invitations() {void this.run(async()=>{this.resendTarget.set(null);this.invitationProgress.set('');this.invitationPreview.set(await this.api.request('/classes/'+this.detail()!.classInfo.id+'/invitations'));});}
  pendingInvitations() {return (this.invitationPreview()?.recipients || []).filter((r:any)=>r.eligible && r.status!=='SENT');}
  sendInvitations(recipients:any[],resend=false) {void this.run(async()=>{
    const classId=this.detail()!.classInfo.id; let sent=0;
    this.resendTarget.set(null);
    try {
      for(let i=0;i<recipients.length;i++) {
        const recipient=recipients[i];this.invitationProgress.set('Enviando '+(i+1)+' de '+recipients.length+' · '+recipient.name);
        const result=await this.api.request<{status:string;message:string}>('/classes/'+classId+'/students/'+recipient.student_id+'/invitation','POST',{request_id:crypto.randomUUID(),resend});
        if(result.status==='SENT') sent++;
        else if(result.status!=='SKIPPED') throw new Error(result.message || 'Envío sin confirmar. Revisa el estado antes de reenviar.');
      }
      this.message.set(sent+' invitaciones aceptadas por el servidor de correo.');
    } finally {
      this.invitationProgress.set('');
      this.invitationPreview.set(await this.api.request('/classes/'+classId+'/invitations'));
    }
  });}
  async copy(url: string) {try {await navigator.clipboard.writeText(url); this.message.set('Enlace copiado.');} catch {this.message.set('Selecciona el enlace y cópialo manualmente.');}}
  downloadLinks() {const cell=(v:string)=>'"'+(/^[=+@\-\t\r]/.test(v)?"'":'')+v.replaceAll('"','""')+'"'; const csv='\ufeffNombre,Enlace\r\n'+this.links().map(x=>[x.name,x.url].map(cell).join(',')).join('\r\n'); const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})); const a=document.createElement('a'); a.href=url; a.download='enlaces-alumnado.csv'; a.click(); URL.revokeObjectURL(url);}
  remove(s:Student) {void this.run(async()=>{await this.api.request(this.studentPath(s),'DELETE',{}); this.selected.set(null); this.links.set([]); await this.refresh(); this.message.set('Alumno retirado de la clase.');});}
  studentPath(s:Student) {return '/classes/'+this.detail()!.classInfo.id+'/students/'+s.id;}
  reopen(s: Student) {void this.run(async () => {await this.api.request(this.studentPath(s)+'/reopen','POST',{}); await this.refresh(); this.message.set('Cuestionario reabierto. Se conserva la revisión anterior.');});}
  select(s:Student) {this.selected.set({...s,observation:{...s.observation}});}
  saveObservation() {void this.run(async () => {await this.api.request(this.studentPath(this.selected()!)+'/observation','POST',this.selected()!.observation); await this.refresh(); this.message.set('Observación guardada.');});}
  saveRelation() {void this.run(async () => {await this.api.request('/classes/'+this.detail()!.classInfo.id+'/relations','POST',this.relation); await this.refresh();});}
  deleteRelation(id:string) {void this.run(async () => {await this.api.request('/classes/'+this.detail()!.classInfo.id+'/relations/'+id,'DELETE',{}); await this.refresh();});}
  name(id:string) {return this.detail()?.students.find(s=>s.id===id)?.name || id;}
  grouping() {this.tab.set('teams'); void this.run(async () => {const id=this.detail()!.classInfo.id; this.history.set(await this.api.request<any[]>('/classes/'+id+'/proposals')); this.options.set([]); this.sizes=''; this.options.set(await this.api.request<any[]>('/classes/'+id+'/size-options')); this.sizes=this.options()[0]?.sizes.join(',') || '';});}
  generate(alternative=false) {void this.run(async () => {const id=this.detail()!.classInfo.id; this.proposal.set(await this.api.request('/classes/'+id+'/proposals','POST',{sizes:this.sizes.split(',').map(Number),reference_id:alternative?this.proposal()?.id:undefined})); this.history.set(await this.api.request<any[]>('/classes/'+id+'/proposals'));});}
  loadProposal(id:string) {void this.run(async () => {this.proposal.set(await this.api.request('/proposals/'+id));});}
  change(action:string, extra:object={}) {void this.run(async () => {const p=this.proposal(); this.proposal.set(await this.api.request('/proposals/'+p.id+'/change','POST',{action,version:p.version,...extra})); this.history.set(await this.api.request<any[]>('/classes/'+this.detail()!.classInfo.id+'/proposals'));});}
  assign() {void this.run(async () => {await this.api.request('/classes/'+this.detail()!.classInfo.id+'/teachers','POST',{email:this.teacherEmail}); await this.refresh(); this.teacherEmail='';});}
  saveClass() {void this.run(async () => {await this.api.request('/classes/'+this.detail()!.classInfo.id,'PATCH',this.detail()!.classInfo); await this.loadClasses(); this.message.set('Clase actualizada.');});}
  deleteClass() {void this.run(async () => {await this.api.request('/classes/'+this.detail()!.classInfo.id,'DELETE',{confirmation:this.deletion}); this.detail.set(null); this.deletion=''; await this.loadClasses();});}
  admin() {this.tab.set('admin'); void this.run(async()=>{this.users.set(await this.api.request<any[]>('/users'));});}
  editUser(user:any) {this.editingUser.set(user.id); this.newUser={email:user.email,name:user.name,role:user.role,active:!!user.active};}
  resetUser() {this.editingUser.set(null);this.newUser={email:'',name:'',role:'TEACHER',active:true};}
  async refreshUsers() {await this.api.session(); if(this.api.user()?.role==='ADMIN') this.users.set(await this.api.request<any[]>('/users')); else {this.users.set([]);this.tab.set('students');} await this.loadClasses();}
  addUser() {void this.run(async()=>{const id=this.editingUser();await this.api.request(id?'/users/'+id:'/users',id?'PATCH':'POST',this.newUser);this.resetUser();await this.refreshUsers();this.message.set('Usuario guardado.');});}
  deleteUser() {void this.run(async()=>{await this.api.request('/users/'+this.deletingUser().id,'DELETE',{});this.deletingUser.set(null);this.resetUser();await this.refreshUsers();this.message.set('Usuario eliminado. Su acceso ha quedado desactivado.');});}
  exportUrl(format:string) {return '/api/classes/'+this.detail()!.classInfo.id+'/export/'+format;}
}
