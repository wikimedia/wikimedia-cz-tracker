( function () {
	var idSupervisorNotes = document.querySelector( '#id_supervisor_notes' );

	function signSupervisor() {
		var param = '\n\nSem napište svou poznámku supervizora anebo tento text smažte --' + window.username;
		idSupervisorNotes.value += param;
	}
	idSupervisorNotes.addEventListener( 'click', function cb() {
		signSupervisor();
		idSupervisorNotes.removeEventListener( 'click', cb );
	} );
}() );
